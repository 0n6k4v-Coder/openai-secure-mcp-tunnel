from __future__ import annotations

import json
import os

from openshell import SandboxClient

from .policy import (
    build_sandbox_spec,
    validate_command,
    validate_name,
)
from ..workspace.service import get_workspace_grant


OPEN_SHELL_GATEWAY = os.environ.get(
    "OPEN_SHELL_GATEWAY",
    "",
)

OPEN_SHELL_WORKSPACE = os.environ.get(
    "OPEN_SHELL_WORKSPACE",
    "default",
)

HOST_WORKSPACE_LABEL = "mcp_host_workspace_id"


class SandboxError(RuntimeError):
    """Raised when an OpenShell sandbox operation fails."""


def _client() -> SandboxClient:
    try:
        if OPEN_SHELL_GATEWAY:
            return SandboxClient(OPEN_SHELL_GATEWAY)

        return SandboxClient.from_active_cluster()

    except Exception as exc:
        raise SandboxError(
            f"Could not connect to the configured OpenShell gateway: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _host_workspace_id_from_labels(
    labels,
) -> str | None:
    if not isinstance(
        labels,
        dict,
    ):
        return None

    value = labels.get(
        HOST_WORKSPACE_LABEL
    )

    if (
        isinstance(
            value,
            str,
        )
        and value
    ):
        return value

    return None


def _host_workspace_metadata(
    host_workspace_id: str | None,
) -> dict[str, object] | None:
    """
    Return only MCP-safe metadata for an authorized host workspace.

    The exact host filesystem path and Docker volume name are intentionally
    excluded from MCP tool results. Those values remain application-only
    implementation details.
    """
    if not host_workspace_id:
        return None

    try:
        grant = get_workspace_grant(
            host_workspace_id
        )
    except ValueError:
        return {
            "workspace_id": host_workspace_id,
            "authorized": False,
        }

    return {
        "workspace_id": host_workspace_id,
        "authorized": True,
        "target": grant["target"],
        "read_only": grant["read_only"],
    }


def _sandbox_to_dict(
    sandbox,
) -> dict[str, object]:
    status = getattr(
        sandbox,
        "status",
        None,
    )

    labels = getattr(
        sandbox,
        "labels",
        None,
    )

    host_workspace_id = _host_workspace_id_from_labels(
        labels
    )

    result: dict[str, object] = {
        "id": getattr(
            sandbox,
            "id",
            None,
        ),
        "name": getattr(
            sandbox,
            "name",
            None,
        ),
        "workspace": OPEN_SHELL_WORKSPACE,
        "phase": getattr(
            sandbox,
            "phase",
            None,
        ),
        "status": getattr(
            status,
            "phase",
            None,
        ),
        "labels": labels,
    }

    if host_workspace_id:
        result["host_workspace_id"] = host_workspace_id

        metadata = _host_workspace_metadata(
            host_workspace_id
        )

        if metadata is not None:
            result["host_workspace"] = metadata

    return result


def create_sandbox(
    name: str,
    workspace_id: str,
) -> str:
    """
    Create and wait for an OpenShell sandbox.

    workspace_id identifies a human-authorized host workspace capability.

    The exact host filesystem path and Docker volume name are resolved by
    the trusted application layer and are never returned to the MCP client.
    """
    name = validate_name(
        name
    )

    if (
        not isinstance(
            workspace_id,
            str,
        )
        or not workspace_id.strip()
    ):
        raise ValueError(
            "host_workspace_id must not be empty."
        )

    try:
        grant = get_workspace_grant(
            workspace_id
        )

        with _client() as client:
            sandbox = client.create(
                workspace=OPEN_SHELL_WORKSPACE,
                name=name,
                labels={
                    HOST_WORKSPACE_LABEL: workspace_id,
                },
                spec=build_sandbox_spec(
                    workspace_id
                ),
            )

            ready = client.wait_ready(
                sandbox.name,
                workspace=OPEN_SHELL_WORKSPACE,
                timeout_seconds=120,
            )

            result = _sandbox_to_dict(
                ready
            )

            result["host_workspace_id"] = workspace_id

            result["host_workspace"] = {
                "workspace_id": workspace_id,
                "authorized": True,
                "target": grant["target"],
                "read_only": grant["read_only"],
            }

            result["project_mount"] = {
                "target": grant["target"],
                "read_only": grant["read_only"],
            }

            return json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to create sandbox '{name}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def list_sandboxes() -> str:
    """List OpenShell sandboxes in the configured OpenShell workspace."""
    try:
        with _client() as client:
            sandboxes = client.list_all(
                workspace=OPEN_SHELL_WORKSPACE,
            )

            return json.dumps(
                [
                    _sandbox_to_dict(
                        sandbox
                    )
                    for sandbox in sandboxes
                ],
                ensure_ascii=False,
                indent=2,
            )

    except Exception as exc:
        raise SandboxError(
            "Failed to list OpenShell sandboxes: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def sandbox_status(
    name: str,
) -> str:
    """Return OpenShell sandbox metadata."""
    name = validate_name(
        name
    )

    try:
        with _client() as client:
            sandboxes = client.list_all(
                workspace=OPEN_SHELL_WORKSPACE,
            )

            for sandbox in sandboxes:
                if sandbox.name == name:
                    return json.dumps(
                        _sandbox_to_dict(
                            sandbox
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to inspect sandbox '{name}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    raise SandboxError(
        f"Sandbox '{name}' was not found."
    )


def execute_sandbox(
    name: str,
    command: str,
    *,
    stdin: bytes | str | None = None,
) -> str:
    """
    Execute a normal command inside an existing sandbox.

    Software installation is deliberately NOT implemented through this
    function. Installation must go through the approval-gated installation
    broker.
    """
    name = validate_name(
        name
    )

    command = validate_command(
        command
    )

    stdin_bytes: bytes | None = None
    if isinstance(stdin, str):
        stdin_bytes = stdin.encode("utf-8")
    elif isinstance(stdin, (bytes, bytearray)):
        stdin_bytes = bytes(stdin)

    try:
        with _client() as client:
            result = client.exec(
                name,
                [
                    "sh",
                    "-lc",
                    command,
                ],
                workspace=OPEN_SHELL_WORKSPACE,
                stdin=stdin_bytes,
            )

            return json.dumps(
                {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.exit_code,
                },
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to execute command in sandbox '{name}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def delete_sandbox(
    name: str,
) -> str:
    """Delete an OpenShell sandbox and wait for deletion to complete."""
    name = validate_name(
        name
    )

    try:
        with _client() as client:
            deletion = client.delete(
                name,
                workspace=OPEN_SHELL_WORKSPACE,
            )

            client.wait_deleted(
                name,
                workspace=OPEN_SHELL_WORKSPACE,
                expected_sandbox_id=deletion.sandbox_id,
            )

            return json.dumps(
                {
                    "name": name,
                    "deleted": True,
                    "sandbox_id": deletion.sandbox_id,
                },
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to delete sandbox '{name}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc