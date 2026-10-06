from __future__ import annotations

import json
import os
import stat
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
import shutil
from typing import Callable

from ..config.paths import (
    app_config_root,
    app_state_root,
    installation_state_file,
    workspace_grants_file,
)
from ..infrastructure.openshell.tls import TLSStatus
from .main import (
    PROJECT_ROOT,
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


def _configured_port(name: str, default: int) -> int:
    """Read and validate a host-published port from the runtime environment."""
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        if os.environ.get("MCP_RUNTIME", "default") != "default":
            from ..runtime.context import get_runtime_context
            profile = get_runtime_context().profile
            runtime_ports = {
                "MCP_PORT": profile.mcp_port,
                "OPENSHELL_PORT": profile.openshell_port,
                "OPENSHELL_HEALTH_PORT": profile.openshell_health_port,
            }
            return runtime_ports.get(name, default)
        return default

    try:
        port = int(raw_value)
    except ValueError as exc:
        raise LifecycleError(
            f"{name} must be an integer port between 1 and 65535."
        ) from exc

    if not 1 <= port <= 65535:
        raise LifecycleError(
            f"{name} must be an integer port between 1 and 65535."
        )

    return port


def _gateway_health_url() -> str:
    return f"http://127.0.0.1:{_configured_port('OPENSHELL_HEALTH_PORT', 8081)}/readyz"


def _mcp_health_url() -> str:
    return f"http://127.0.0.1:{_configured_port('MCP_PORT', 8000)}/healthz"


def _health_request(url: str) -> urllib.request.Request:
    # The MCP health route deliberately allows its fixed internal service Host.
    # The published host port can differ between development and production.
    headers = {"Host": "127.0.0.1:8000"} if url.endswith("/healthz") else {}
    return urllib.request.Request(url, method="GET", headers=headers)


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
        return all(client.configured for client in self.mcp_clients if client.required)

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
        and "api_key: file:/run/secrets/CONTROL_PLANE_API_KEY" in config_content
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
                raise LifecycleError(f"Runtime state path is not a directory: {path}")
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
            raise LifecycleError(f"Runtime state path is not a regular file: {path}")

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




@dataclass(frozen=True)
class LocalImageStatus:
    variable: str
    image: str
    state: str
    dockerfile_dir: Path

    @property
    def available(self) -> bool:
        return self.state == "FOUND"


_LOCAL_IMAGE_DEFAULTS = (
    ("SANDBOX_IMAGE", "local-mcp-openshell-sandbox:1.0.0", "openshell-sandbox"),
    ("BROWSER_SANDBOX_IMAGE", "local-mcp-browser-sandbox:1.0.0", "browser-sandbox"),
    ("WORKSPACE_ACL_HELPER_IMAGE", "local-mcp-workspace-acl-helper:1.0.0", "workspace-acl-helper"),
)


def _configured_image_value(variable: str, default: str) -> str:
    value = os.environ.get(variable)
    if value and value.strip():
        return value.strip()

    env_files: list[Path] = []
    try:
        from ..runtime.context import get_runtime_context

        context_env = get_runtime_context().config_root / ".env"
        env_files.append(context_env)
    except (OSError, RuntimeError, ValueError):
        pass
    env_files.append(PROJECT_ROOT / ".env")

    for env_file in env_files:
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            if key.strip() != variable:
                continue
            value = raw_value.strip().strip('"').strip("'")
            if value:
                return value
    return default


def _local_image_specs() -> tuple[tuple[str, str, Path], ...]:
    return tuple(
        (
            variable,
            _configured_image_value(variable, default),
            PROJECT_ROOT / "deploy" / "docker" / dockerfile_dir,
        )
        for variable, default, dockerfile_dir in _LOCAL_IMAGE_DEFAULTS
    )


def get_local_image_statuses(
    required_variables: tuple[str, ...] | None = None,
) -> tuple[LocalImageStatus, ...]:
    """Inspect effective local image tags without building or changing resources."""
    specs = [
        spec for spec in _local_image_specs()
        if required_variables is None or spec[0] in required_variables
    ]
    if shutil.which("docker") is None:
        return tuple(
            LocalImageStatus(variable, image, "BLOCKED (DOCKER CLI MISSING)", path)
            for variable, image, path in specs
        )

    daemon = _run_capture(["docker", "info", "--format", "{{.ServerVersion}}"])
    if daemon.returncode != 0:
        detail = (daemon.stderr or daemon.stdout).strip()
        state = "BLOCKED (DOCKER DAEMON UNAVAILABLE)"
        if detail:
            state = "BLOCKED (DOCKER DAEMON UNAVAILABLE)"
        return tuple(
            LocalImageStatus(variable, image, state, path)
            for variable, image, path in specs
        )

    statuses: list[LocalImageStatus] = []
    for variable, image, path in specs:
        inspected = _run_capture(["docker", "image", "inspect", image])
        statuses.append(
            LocalImageStatus(variable, image, "FOUND" if inspected.returncode == 0 else "MISSING", path)
        )
    return tuple(statuses)


def print_local_image_statuses(statuses: tuple[LocalImageStatus, ...]) -> None:
    from .main import _print_table

    print("Custom Images")
    _print_table(
        ["IMAGE VARIABLE", "TAG", "STATUS"],
        [[status.variable, status.image, status.state] for status in statuses],
    )


def verify_local_images(required_variables: tuple[str, ...] | None = None) -> None:
    statuses = get_local_image_statuses(required_variables)
    blocked = [status for status in statuses if status.state.startswith("BLOCKED")]
    if blocked:
        raise LifecycleError(
            "Cannot verify local images: " + "; ".join(status.state for status in blocked)
        )
    missing = [status for status in statuses if not status.available]
    if missing:
        details = ", ".join(status.image for status in missing)
        raise LifecycleError(
            f"Required local image(s) missing: {details}. Run 'mcpctl setup' to build them."
        )


def ensure_local_images(
    required_variables: tuple[str, ...] | None = None,
) -> tuple[LocalImageStatus, ...]:
    """Build missing local images and verify every requested tag after the build."""
    specs = [
        spec for spec in _local_image_specs()
        if required_variables is None or spec[0] in required_variables
    ]
    if shutil.which("docker") is None:
        raise LifecycleError("Docker CLI is required to build local sandbox images.")
    daemon = _run_capture(["docker", "info", "--format", "{{.ServerVersion}}"])
    if daemon.returncode != 0:
        detail = (daemon.stderr or daemon.stdout).strip() or "Docker daemon is unavailable."
        raise LifecycleError(f"Cannot build local images: {detail}")

    for variable, image, dockerfile_dir in specs:
        inspected = _run_capture(["docker", "image", "inspect", image])
        if inspected.returncode == 0:
            print(f"      {image}  FOUND (build skipped)")
            continue
        if not dockerfile_dir.is_dir():
            raise LifecycleError(
                f"Cannot build {image}: Docker build context not found: {dockerfile_dir}"
            )
        print(f"      {image}  BUILDING")
        built = _run_capture(["docker", "build", "--tag", image, str(dockerfile_dir)])
        if built.returncode != 0:
            detail = (built.stderr or built.stdout).strip() or "Docker build failed."
            raise LifecycleError(f"Build failed for {image}: {detail}")
        verified = _run_capture(["docker", "image", "inspect", image])
        if verified.returncode != 0:
            raise LifecycleError(
                f"Docker build returned success but image verification failed: {image}"
            )
        print(f"      {image}  BUILT AND VERIFIED")

    statuses = get_local_image_statuses(required_variables)
    missing = [status.image for status in statuses if not status.available]
    if missing:
        raise LifecycleError("Local image verification failed: " + ", ".join(missing))
    return statuses


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

        raise LifecycleError(f"Docker Compose configuration is invalid: {diagnostic}")


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
            raise LifecycleError("Docker Compose returned an unexpected status record.")

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
        request = _health_request(url)

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
            request = _health_request(url)

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

    raise LifecycleError(f"Timed out waiting for {url}: {last_error}")


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
        f"Timed out waiting for Docker Compose service '{service}' to start."
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
        raise LifecycleError("Failed to start OpenShell Gateway and MCP Server.")

    _wait_for_service_running("openshell-gateway")
    _wait_for_http(_gateway_health_url())

    _wait_for_service_running("mcp-server")
    _wait_for_http(_mcp_health_url())


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
        raise LifecycleError("Failed to start the tunnel client.")


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

        raise LifecycleError(f"Unable to remove tunnel client: {diagnostic}")


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
    return tuple(_client_status(definition) for definition in MCP_CLIENT_DEFINITIONS)


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
            health=("healthy" if _http_healthy(_gateway_health_url()) else "unhealthy"),
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
            elif tunnel_client.running:
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
                "✓ READY" if status.tls.complete else "✗ NOT READY",
            ],
            [
                "OpenShell Gateway",
                "✓ READY"
                if (status.gateway.running and status.gateway.health == "healthy")
                else "✗ NOT READY",
            ],
            [
                "MCP Server",
                "✓ READY"
                if (status.mcp_server.running and status.mcp_server.health == "healthy")
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
                ("✓ CONFIGURED" if client.configured else "○ NOT CONFIGURED"),
                client.runtime,
            ]
        )

    _print_table(
        ["#", "CLIENT", "CONFIGURATION", "RUNTIME"],
        client_rows,
    )

    insecure_paths = [
        path for client in status.mcp_clients for path in client.insecure_paths
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
            "Core infrastructure is not ready. Run 'mcpctl status' for details."
        )

    return status
