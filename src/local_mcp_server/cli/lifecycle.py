from __future__ import annotations

import json
import os
import stat
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ..config.paths import (
    app_config_root,
    app_state_root,
    installation_state_file,
    workspace_grants_file,
)
from ..infrastructure.openshell.tls import TLSStatus
from .main import (
    _command_exists,
    _compose_command,
    _run_capture,
    _run_passthrough,
)


DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0

GATEWAY_HEALTH_URL = "http://127.0.0.1:8081/readyz"
MCP_HEALTH_URL = "http://127.0.0.1:8000/healthz"

MCP_CLIENT_SERVICES = ("tunnel-client",)
CORE_SERVICES = ("openshell-gateway", "mcp-server")


class LifecycleError(RuntimeError):
    """Raised when application lifecycle management cannot proceed."""


@dataclass(frozen=True)
class MCPClientStatus:
    configured: bool
    config_file: Path
    credentials_file: Path
    insecure_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ServiceStatus:
    service: str
    state: str
    health: str

    @property
    def running(self) -> bool:
        return self.state.lower() == "running"

    @property
    def healthy(self) -> bool:
        health = self.health.lower()
        return health in {"healthy", "running", ""}


@dataclass(frozen=True)
class LifecycleStatus:
    tls: TLSStatus
    mcp_client: MCPClientStatus
    gateway: ServiceStatus
    mcp_server: ServiceStatus
    tunnel_client: ServiceStatus

    @property
    def infrastructure_ready(self) -> bool:
        return (
            self.tls.complete
            and self.gateway.running
            and self.gateway.health == "healthy"
            and self.mcp_server.running
            and self.mcp_server.health == "healthy"
        )

    @property
    def ready(self) -> bool:
        return (
            self.infrastructure_ready
            and self.mcp_client.configured
            and self.tunnel_client.running
            and self.tunnel_client.health == "running"
        )


def _ensure_private_directory(path: Path) -> None:
    try:
        if path.exists():
            if not path.is_dir():
                raise LifecycleError(
                    f"Runtime state path is not a directory: {path}"
                )
        else:
            path.mkdir(
                parents=True,
                exist_ok=True,
                mode=0o700,
            )

        mode = stat.S_IMODE(path.stat().st_mode)

    except LifecycleError:
        raise

    except OSError as exc:
        raise LifecycleError(
            f"Unable to prepare runtime directory {path}: {exc}"
        ) from exc

    if mode & 0o077:
        raise LifecycleError(
            f"Runtime directory {path} must not be accessible "
            f"by group or other users; current mode is {mode:04o}."
        )


def _ensure_private_file(path: Path, content: str) -> None:
    _ensure_private_directory(path.parent)

    if path.exists():
        if not path.is_file():
            raise LifecycleError(
                f"Runtime state path is not a regular file: {path}"
            )

        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError as exc:
            raise LifecycleError(
                f"Unable to inspect runtime state file {path}: {exc}"
            ) from exc

        if mode & 0o077:
            raise LifecycleError(
                f"Runtime state file {path} must not be accessible "
                f"by group or other users; current mode is {mode:04o}."
            )

        return

    temporary = path.with_name(f".{path.name}.tmp")

    try:
        temporary.write_text(
            content,
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

        raise LifecycleError(
            f"Unable to initialize runtime state file {path}: {exc}"
        ) from exc


def prepare_runtime() -> None:
    config_root = app_config_root()
    state_root = app_state_root()

    directories = (
        config_root,
        config_root / "mcp-clients",
        state_root,
        state_root / "config",
        state_root / "config" / "credentials",
        state_root / "openshell",
        state_root / "openshell" / "tls",
        state_root / "mcp",
        state_root / "mcp" / "workspace-grants",
        state_root / "logs",
    )

    for directory in directories:
        _ensure_private_directory(directory)

    _ensure_private_file(
        installation_state_file(),
        "{}\n",
    )
    _ensure_private_file(
        workspace_grants_file(),
        "{}\n",
    )


def validate_compose() -> None:
    _command_exists("docker")

    result = _run_capture(
        _compose_command(
            "config",
            "--quiet",
        )
    )

    if result.returncode != 0:
        diagnostic = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Docker Compose configuration validation failed."
        )

        raise LifecycleError(
            f"Docker Compose configuration is invalid: {diagnostic}"
        )


def _service_statuses() -> dict[str, ServiceStatus]:
    result = _run_capture(
        _compose_command(
            "ps",
            "--all",
            "--format",
            "json",
        )
    )

    if result.returncode != 0:
        diagnostic = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Docker Compose status query failed."
        )

        raise LifecycleError(
            f"Unable to query Docker Compose service state: {diagnostic}"
        )

    statuses: dict[str, ServiceStatus] = {}

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LifecycleError(
                "Docker Compose returned invalid JSON status output."
            ) from exc

        if not isinstance(record, dict):
            raise LifecycleError(
                "Docker Compose returned an unexpected status record."
            )

        service = record.get("Service")
        state = record.get("State")
        health = record.get("Health")

        if not isinstance(service, str):
            continue

        statuses[service] = ServiceStatus(
            service=service,
            state=str(state or "unknown"),
            health=str(health or ""),
        )

    return statuses


def _service_status(
    statuses: dict[str, ServiceStatus],
    service: str,
) -> ServiceStatus:
    return statuses.get(
        service,
        ServiceStatus(
            service=service,
            state="not running",
            health="",
        ),
    )


def _wait_for_http(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "endpoint did not respond"

    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(
                url,
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=3,
            ) as response:
                if response.status == 200:
                    return

                last_error = f"HTTP {response.status}"

        except (
            OSError,
            urllib.error.URLError,
        ) as exc:
            last_error = str(exc)

        time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)

    raise LifecycleError(
        f"Timed out waiting for {url}: {last_error}"
    )


def _wait_for_service_running(
    service: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        statuses = _service_statuses()
        status = _service_status(statuses, service)

        if status.running:
            return

        time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)

    raise LifecycleError(
        f"Timed out waiting for Docker Compose service "
        f"'{service}' to start."
    )


def start_core_services() -> None:
    result = _run_passthrough(
        _compose_command(
            "up",
            "--build",
            "--remove-orphans",
            "--detach",
            *CORE_SERVICES,
        )
    )

    if result != 0:
        raise LifecycleError(
            "Failed to start OpenShell Gateway and MCP Server."
        )

    _wait_for_service_running("openshell-gateway")
    _wait_for_http(GATEWAY_HEALTH_URL)

    _wait_for_service_running("mcp-server")
    _wait_for_http(MCP_HEALTH_URL)


def start_tunnel_client() -> None:
    result = _run_passthrough(
        _compose_command(
            "up",
            "--build",
            "--remove-orphans",
            "--detach",
            "tunnel-client",
        )
    )

    if result != 0:
        raise LifecycleError(
            "Failed to start the tunnel client."
        )


def remove_tunnel_client() -> None:
    result = _run_capture(
        _compose_command(
            "rm",
            "--force",
            "tunnel-client",
        )
    )

    if result.returncode != 0:
        diagnostic = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Docker Compose could not remove the tunnel client."
        )

        raise LifecycleError(
            f"Unable to remove tunnel client: {diagnostic}"
        )


def _expected_private_paths() -> tuple[Path, ...]:
    from ..config.paths import (
        mcp_clients_root,
        openai_api_key_file,
        openai_config_file,
        openai_root,
    )

    return (
        app_config_root(),
        mcp_clients_root(),
        openai_root(),
        openai_config_file(),
        openai_api_key_file(),
    )


def get_mcp_client_status() -> MCPClientStatus:
    from ..config.paths import (
        openai_api_key_file,
        openai_config_file,
    )

    config_file = openai_config_file()
    credentials_file = openai_api_key_file()

    insecure: list[Path] = []

    for path in _expected_private_paths():
        if not path.exists():
            continue

        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            insecure.append(path)
            continue

        if path.is_dir():
            if mode & 0o077:
                insecure.append(path)
        elif mode & 0o077:
            insecure.append(path)

    configured = False

    if (
        config_file.is_file()
        and credentials_file.is_file()
        and not insecure
    ):
        try:
            config_content = config_file.read_text(
                encoding="utf-8",
            )
            credential_content = credentials_file.read_text(
                encoding="utf-8",
            ).strip()
        except OSError:
            configured = False
        else:
            configured = (
                bool(credential_content)
                and "\n" not in credential_content
                and "\r" not in credential_content
                and "config_version: 1" in config_content
                and "base_url: https://api.openai.com" in config_content
                and "api_key: file:/run/secrets/CONTROL_PLANE_API_KEY"
                in config_content
                and "url: http://mcp-server:8000/mcp" in config_content
            )

    return MCPClientStatus(
        configured=configured,
        config_file=config_file,
        credentials_file=credentials_file,
        insecure_paths=tuple(insecure),
    )


def reconcile_tunnel_client() -> None:
    client = get_mcp_client_status()

    if client.configured:
        start_tunnel_client()
        return

    remove_tunnel_client()


def get_status(
    tls: TLSStatus,
) -> LifecycleStatus:
    statuses = _service_statuses()

    return LifecycleStatus(
        tls=tls,
        mcp_client=get_mcp_client_status(),
        gateway=_service_status(
            statuses,
            "openshell-gateway",
        ),
        mcp_server=_service_status(
            statuses,
            "mcp-server",
        ),
        tunnel_client=_service_status(
            statuses,
            "tunnel-client",
        ),
    )


def print_status(status: LifecycleStatus) -> None:
    print("Local MCP Lifecycle")
    print()

    print(
        "OpenShell TLS:        "
        + ("READY" if status.tls.complete else "NOT READY")
    )

    print(
        "OpenShell Gateway:    "
        + (
            "READY"
            if status.gateway.running
            and status.gateway.health == "healthy"
            else "NOT READY"
        )
    )

    print(
        "MCP Server:            "
        + (
            "READY"
            if status.mcp_server.running
            and status.mcp_server.health == "healthy"
            else "NOT READY"
        )
    )

    if status.mcp_client.configured:
        print("MCP Client Configuration: READY")
    else:
        print("MCP Client Configuration: NOT CONFIGURED")
        print("  Action: mcpctl config mcp-client")

    if status.mcp_client.insecure_paths:
        print("  Permissions: NOT SECURE")
        for path in status.mcp_client.insecure_paths:
            print(f"    - {path}")

    if status.mcp_client.configured:
        print(
            "Tunnel Client:         "
            + (
                "READY"
                if status.tunnel_client.running
                else "NOT RUNNING"
            )
        )
    else:
        print("Tunnel Client:         NOT CONFIGURED")

    print()

    if status.ready:
        print("Overall: READY")
    elif status.infrastructure_ready and not status.mcp_client.configured:
        print("Overall: PARTIALLY READY")
    else:
        print("Overall: NOT READY")


def verify(
    tls: TLSStatus,
) -> LifecycleStatus:
    status = get_status(tls)

    if not status.infrastructure_ready:
        raise LifecycleError(
            "Core infrastructure is not ready. "
            "Run 'mcpctl status' for details."
        )

    return status