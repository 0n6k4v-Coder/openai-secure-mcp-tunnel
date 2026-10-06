from __future__ import annotations

from openshell import SandboxClient


class OpenShellConnectionError(RuntimeError):
    """Raised when the configured OpenShell gateway cannot be reached."""


def active_client() -> SandboxClient:
    from ...runtime.context import get_runtime_context
    runtime = get_runtime_context()
    try:
        return SandboxClient.from_active_cluster()
    except Exception as exc:
        raise OpenShellConnectionError(
            f"Could not connect to the configured OpenShell gateway for runtime "
            f"{runtime.profile.name!r}: {type(exc).__name__}: {exc}"
        ) from exc
