from __future__ import annotations

import json
import os
import re

from openshell import SandboxClient
from openshell._proto import openshell_pb2

from .workspace import resolve_workspace_grant


OPEN_SHELL_GATEWAY = os.environ.get(
    "OPEN_SHELL_GATEWAY",
    "",
)
OPEN_SHELL_WORKSPACE = os.environ.get(
    "OPEN_SHELL_WORKSPACE",
    "default",
)
SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE",
    "local-mcp-openshell-sandbox:1.0.0",
)
DEFAULT_CPU = os.environ.get(
    "SANDBOX_DEFAULT_CPU",
    "1",
)
DEFAULT_MEMORY = os.environ.get(
    "SANDBOX_DEFAULT_MEMORY",
    "1Gi",
)
MAX_COMMAND_BYTES = 32 * 1024

_SANDBOX_NAME = re.compile(
    r"^[a-z0-9][a-z0-9-]{0,62}$"
)
_CPU_QUANTITY = re.compile(
    r"^(?:\d+(?:\.\d+)?|\d+m)$"
)
_MEMORY_QUANTITY = re.compile(
    r"^\d+(?:\.\d+)?(?:Ki|Mi|Gi|Ti|Pi|Ei|K|M|G|T|P|E)$"
)


class SandboxError(RuntimeError):
    """Raised when an OpenShell sandbox operation fails."""


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not _SANDBOX_NAME.fullmatch(name):
        raise ValueError(
            "sandbox name must contain only lowercase letters, digits, "
            "and hyphens, start with a letter or digit, and be at most "
            "63 characters"
        )

    return name


def _validate_cpu(value: str) -> str:
    if not isinstance(value, str) or not _CPU_QUANTITY.fullmatch(value):
        raise ValueError(
            "CPU must be a Kubernetes-style quantity such as "
            "500m, 1, or 2.5"
        )

    return value


def _validate_memory(value: str) -> str:
    if (
        not isinstance(value, str)
        or not _MEMORY_QUANTITY.fullmatch(value)
    ):
        raise ValueError(
            "memory must be a quantity such as "
            "512Mi, 4Gi, or 8G"
        )

    return value


def _validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ValueError(
            "command must not be empty"
        )

    if len(command.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise ValueError(
            f"command exceeds {MAX_COMMAND_BYTES} bytes"
        )

    return command


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


def _build_sandbox_spec(
    workspace_id: str,
) -> openshell_pb2.SandboxSpec:
    """
    Build the OpenShell sandbox specification.

    The host path is never supplied directly by the model. It is resolved
    through an opaque, previously authorized workspace capability.
    """
    cpu = _validate_cpu(
        DEFAULT_CPU
    )
    memory = _validate_memory(
        DEFAULT_MEMORY
    )

    host_workspace = resolve_workspace_grant(
        workspace_id
    )

    spec = openshell_pb2.SandboxSpec()

    spec.template.image = SANDBOX_IMAGE

    spec.template.resources.update(
        {
            "limits": {
                "cpu": cpu,
                "memory": memory,
            }
        }
    )

    spec.template.driver_config.update(
        {
            "docker": {
                "mounts": [
                    {
                        "type": "bind",
                        "source": str(host_workspace),
                        "target": "/workspace/project",
                        "read_only": False,
                    }
                ]
            }
        }
    )

    return spec


def create_sandbox(
    name: str,
    workspace_id: str,
) -> str:
    """Create and wait for an OpenShell sandbox."""
    name = _validate_name(
        name
    )

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
                spec=_build_sandbox_spec(
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
    name = _validate_name(
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
    name = _validate_name(
        name
    )
    command = _validate_command(
        command
    )

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
    name = _validate_name(
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
            f"Failed to delete sandbox '{name}'."
        ) from exc