from __future__ import annotations

import json
import os

from openshell import SandboxClient

from .policy import (
    build_sandbox_spec,
    validate_command,
    validate_name,
)


OPEN_SHELL_GATEWAY = os.environ.get(
    "OPEN_SHELL_GATEWAY",
    "",
)

OPEN_SHELL_WORKSPACE = os.environ.get(
    "OPEN_SHELL_WORKSPACE",
    "default",
)


class SandboxError(RuntimeError):
    """Raised when an OpenShell sandbox operation fails."""


def _client() -> SandboxClient:
    try:
        if OPEN_SHELL_GATEWAY:
            return SandboxClient(
                OPEN_SHELL_GATEWAY
            )

        return SandboxClient.from_active_cluster()

    except Exception as exc:
        raise SandboxError(
            "Could not connect to the configured "
            "OpenShell gateway."
        ) from exc


def _sandbox_to_dict(
    sandbox,
) -> dict[str, object]:
    status = getattr(
        sandbox,
        "status",
        None,
    )

    return {
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
        "labels": getattr(
            sandbox,
            "labels",
            None,
        ),
    }


def create_sandbox(
    name: str,
    workspace_id: str,
) -> str:
    """Create and wait for an OpenShell sandbox."""
    name = validate_name(name)

    if not isinstance(
        workspace_id,
        str,
    ) or not workspace_id.strip():
        raise ValueError(
            "workspace_id must not be empty."
        )

    try:
        with _client() as client:
            sandbox = client.create(
                workspace=OPEN_SHELL_WORKSPACE,
                name=name,
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

            result["workspace_id"] = workspace_id

            result["project_mount"] = {
                "target": "/workspace/project",
                "read_only": False,
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
            f"Failed to create sandbox '{name}'."
        ) from exc


def list_sandboxes() -> str:
    """List OpenShell sandboxes in the configured workspace."""
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
            "Failed to list OpenShell sandboxes."
        ) from exc


def sandbox_status(
    name: str,
) -> str:
    """Return OpenShell sandbox metadata."""
    name = validate_name(name)

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
            f"Failed to inspect sandbox '{name}'."
        ) from exc

    raise SandboxError(
        f"Sandbox '{name}' was not found."
    )


def execute_sandbox(
    name: str,
    command: str,
) -> str:
    """
    Execute a normal command inside an existing sandbox.

    Software installation is deliberately NOT implemented through this
    function. Installation must go through the approval-gated installation
    broker.
    """
    name = validate_name(name)
    command = validate_command(command)

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
            f"Failed to execute command in sandbox '{name}'."
        ) from exc


def delete_sandbox(
    name: str,
) -> str:
    """Delete an OpenShell sandbox and wait for deletion to complete."""
    name = validate_name(name)

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
            f"Failed to delete sandbox '{name}'."
        ) from exc