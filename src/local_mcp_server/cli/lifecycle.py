from __future__ import annotations

import json
import os
import stat
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

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
class MCPClientDefinition:
    key: str
    display_name: str
    required: bool
    config_file: Callable[[], Path]
    credentials_file: Callable[[], Path]
    private_paths: Callable[[], tuple[Path, ...]]
    validator: Callable[[Path, Path], bool]


@dataclass(frozen=True)
class MCPClientStatus:
    key: str
    display_name: str
    required: bool
    configured: bool
    config_present: bool
    credentials_present: bool
    permissions_secure: bool | None
    config_file: Path
    credentials_file: Path
    insecure_paths: tuple[Path, ...]
    runtime: str = "—"

    @property
    def available(self) -> bool:
        return True


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
    mcp_clients: tuple[MCPClientStatus, ...]
    gateway: ServiceStatus
    mcp_server: ServiceStatus
    tunnel_client: ServiceStatus

    @property
    def mcp_client(self) -> MCPClientStatus:
        """Return the first registered MCP client for compatibility."""
        if not self.mcp_clients:
            raise LifecycleError("No MCP clients are registered.")

        return self.mcp_clients[0]

    @property
    def required_mcp_clients_configured(self) -> bool:
        return all(
            client.configured
            for client in self.mcp_clients
            if client.required
        )

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
            and self.required_mcp_clients_configured
            and self.tunnel_client.running
            and self.tunnel_client.health == "running"
        )


def _openai_config_file() -> Path:
    from ..config.paths import openai_config_file

    return openai_config_file()


def _openai_credentials_file() -> Path:
    from ..config.paths import openai_api_key_file

    return openai_api_key_file()


def _openai_private_paths() -> tuple[Path, ...]:
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


def _validate_openai_configuration(
    config_file: Path,
    credentials_file: Path,
) -> bool:
    if not config_file.is_file() or not credentials_file.is_file():
        return False

    try:
        config_content = config_file.read_text(
            encoding="utf-8",
        )
        credential_content = credentials_file.read_text(
            encoding="utf-8",
        ).strip()
    except OSError:
        return False

    return (
        bool(credential_content)
        and "\n" not in credential_content
        and "\r" not in credential_content
        and "config_version: 1" in config_content
        and "base_url: https://api.openai.com" in config_content
        and "api_key: file:/run/secrets/CONTROL_PLANE_API_KEY"
        in config_content
        and "url: http://mcp-server:8000/mcp" in config_content
    )


MCP_CLIENT_DEFINITIONS = (
    MCPClientDefinition(
        key="openai",
        display_name="OpenAI",
        required=True,
        config_file=_openai_config_file,
        credentials_file=_openai_credentials_file,
        private_paths=_openai_private_paths,
        validator=_validate_openai_configuration,
    ),
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


def _http_healthy(
    url: str,
    *,
    timeout_seconds: float = 3.0,
) -> bool:
    """Return whether an HTTP readiness endpoint responds with HTTP 200."""
    try:
        request = urllib.request.Request(
            url,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            return response.status == 200

    except (
        OSError,
        urllib.error.URLError,
    ):
        return False


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


def _client_permissions(
    definition: MCPClientDefinition,
) -> tuple[Path, ...]:
    insecure: list[Path] = []

    for path in definition.private_paths():
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

    return tuple(insecure)


def _client_status(
    definition: MCPClientDefinition,
    *,
    runtime: str = "—",
) -> MCPClientStatus:
    config_file = definition.config_file()
    credentials_file = definition.credentials_file()

    insecure_paths = _client_permissions(definition)

    config_present = config_file.is_file()
    credentials_present = credentials_file.is_file()

    if not config_present and not credentials_present:
        permissions_secure: bool | None = None
    else:
        permissions_secure = not insecure_paths

    configured = (
        config_present
        and credentials_present
        and not insecure_paths
        and definition.validator(
            config_file,
            credentials_file,
        )
    )

    return MCPClientStatus(
        key=definition.key,
        display_name=definition.display_name,
        required=definition.required,
        configured=configured,
        config_present=config_present,
        credentials_present=credentials_present,
        permissions_secure=permissions_secure,
        config_file=config_file,
        credentials_file=credentials_file,
        insecure_paths=insecure_paths,
        runtime=runtime,
    )


def get_mcp_client_statuses() -> tuple[MCPClientStatus, ...]:
    return tuple(
        _client_status(definition)
        for definition in MCP_CLIENT_DEFINITIONS
    )


def get_mcp_client_status() -> MCPClientStatus:
    """Return the first registered MCP client for compatibility."""
    statuses = get_mcp_client_statuses()

    if not statuses:
        raise LifecycleError("No MCP clients are registered.")

    return statuses[0]


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

    gateway = _service_status(
        statuses,
        "openshell-gateway",
    )

    if gateway.running:
        gateway = replace(
            gateway,
            health=(
                "healthy"
                if _http_healthy(GATEWAY_HEALTH_URL)
                else "unhealthy"
            ),
        )

    mcp_server = _service_status(
        statuses,
        "mcp-server",
    )

    tunnel_client = _service_status(
        statuses,
        "tunnel-client",
    )

    client_statuses: list[MCPClientStatus] = []

    for client in get_mcp_client_statuses():
        runtime = "—"

        if client.key == "openai":
            if not client.configured:
                runtime = "—"
            elif (
                tunnel_client.running
                and tunnel_client.health == "running"
            ):
                runtime = "✓ ACTIVE"
            else:
                runtime = "○ NOT RUNNING"

        client_statuses.append(
            replace(
                client,
                runtime=runtime,
            )
        )

    return LifecycleStatus(
        tls=tls,
        mcp_clients=tuple(client_statuses),
        gateway=gateway,
        mcp_server=mcp_server,
        tunnel_client=tunnel_client,
    )


def print_status(status: LifecycleStatus) -> None:
    from .main import _print_table

    print("Local MCP Lifecycle")
    print()

    print("Infrastructure")
    print()

    _print_table(
        ["COMPONENT", "STATUS"],
        [
            [
                "Runtime",
                "✓ READY",
            ],
            [
                "OpenShell TLS",
                "✓ READY"
                if status.tls.complete
                else "✗ NOT READY",
            ],
            [
                "OpenShell Gateway",
                "✓ READY"
                if (
                    status.gateway.running
                    and status.gateway.health == "healthy"
                )
                else "✗ NOT READY",
            ],
            [
                "MCP Server",
                "✓ READY"
                if (
                    status.mcp_server.running
                    and status.mcp_server.health == "healthy"
                )
                else "✗ NOT READY",
            ],
        ],
    )

    print()
    print("MCP Clients")
    print()

    client_rows: list[list[str]] = []

    for index, client in enumerate(
        status.mcp_clients,
        start=1,
    ):
        client_rows.append(
            [
                str(index),
                client.display_name,
                (
                    "✓ CONFIGURED"
                    if client.configured
                    else "○ NOT CONFIGURED"
                ),
                client.runtime,
            ]
        )

    _print_table(
        ["#", "CLIENT", "CONFIGURATION", "RUNTIME"],
        client_rows,
    )

    insecure_paths = [
        path
        for client in status.mcp_clients
        for path in client.insecure_paths
    ]

    if insecure_paths:
        print()
        print("Permissions")
        print()

        for path in insecure_paths:
            print(f"  ✗ INSECURE  {path}")

    print()
    print("Overall")

    if status.ready:
        print("✓ READY")
        print()
        print("Next step:")
        print("  None. Local MCP Server is ready.")
        return

    if status.infrastructure_ready:
        print("⚠ PARTIALLY READY")

        if not status.required_mcp_clients_configured:
            print()
            print("Next step:")
            print("  mcpctl config mcp-client")
        else:
            print()
            print("Next step:")
            print("  mcpctl repair")

        return

    print("✗ NOT READY")
    print()
    print("Next step:")
    print("  mcpctl repair")


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