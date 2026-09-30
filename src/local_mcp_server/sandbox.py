from __future__ import annotations

import json
import os
import re

from openshell import SandboxClient


OPEN_SHELL_WORKSPACE = os.environ.get("OPEN_SHELL_WORKSPACE", "default")
SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE",
    "local-mcp-openshell-sandbox:1.0.0",
)
DEFAULT_CPU = os.environ.get("SANDBOX_DEFAULT_CPU", "1")
DEFAULT_MEMORY = os.environ.get("SANDBOX_DEFAULT_MEMORY", "1GiB")
MAX_COMMAND_BYTES = 32 * 1024
_SANDBOX_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class SandboxError(RuntimeError):
    """Raised when an OpenShell sandbox operation fails."""


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not _SANDBOX_NAME.fullmatch(name):
        raise ValueError(
            "sandbox name must contain only lowercase letters, digits, and "
            "hyphens, start with a letter or digit, and be at most 63 characters"
        )

    return name


def _validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must not be empty")

    if len(command.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise ValueError(f"command exceeds {MAX_COMMAND_BYTES} bytes")

    return command


def _client() -> SandboxClient:
    try:
        return SandboxClient.from_active_cluster()
    except Exception as exc:
        raise SandboxError(
            "Could not connect to the configured OpenShell gateway."
        ) from exc


def _sandbox_to_dict(sandbox) -> dict[str, object]:
    return {
        "id": getattr(sandbox, "id", None),
        "name": getattr(sandbox, "name", None),
        "workspace": getattr(sandbox, "workspace", OPEN_SHELL_WORKSPACE),
        "phase": getattr(sandbox, "phase", None),
        "labels": getattr(sandbox, "labels", None),
    }


def create_sandbox(name: str) -> str:
    """Create a policy-enforced OpenShell sandbox."""
    name = _validate_name(name)

    try:
        with _client() as client:
            sandbox = client.create(
                workspace=OPEN_SHELL_WORKSPACE,
                name=name,
                image=SANDBOX_IMAGE,
                cpu=DEFAULT_CPU,
                memory=DEFAULT_MEMORY,
            )

            client.wait_ready(
                sandbox.name,
                workspace=OPEN_SHELL_WORKSPACE,
                timeout_seconds=120,
            )

            return json.dumps(
                _sandbox_to_dict(sandbox),
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise
    except Exception as exc:
        raise SandboxError(f"Failed to create sandbox '{name}'.") from exc


def list_sandboxes() -> str:
    """List OpenShell sandboxes in the configured workspace."""
    try:
        with _client() as client:
            sandboxes = client.list_all(
                workspace=OPEN_SHELL_WORKSPACE,
            )

            return json.dumps(
                [_sandbox_to_dict(sandbox) for sandbox in sandboxes],
                ensure_ascii=False,
                indent=2,
            )

    except Exception as exc:
        raise SandboxError("Failed to list OpenShell sandboxes.") from exc


def sandbox_status(name: str) -> str:
    """Return OpenShell sandbox metadata."""
    name = _validate_name(name)

    try:
        with _client() as client:
            sandboxes = client.list_all(
                workspace=OPEN_SHELL_WORKSPACE,
            )

            for sandbox in sandboxes:
                if sandbox.name == name:
                    return json.dumps(
                        _sandbox_to_dict(sandbox),
                        ensure_ascii=False,
                        indent=2,
                    )

    except ValueError:
        raise
    except Exception as exc:
        raise SandboxError(f"Failed to inspect sandbox '{name}'.") from exc

    raise SandboxError(f"Sandbox '{name}' was not found.")


def execute_sandbox(
    name: str,
    command: str,
) -> str:
    """Execute a command inside an existing OpenShell sandbox."""
    name = _validate_name(name)
    command = _validate_command(command)

    try:
        with _client() as client:
            result = client.exec(
                name,
                ["sh", "-lc", command],
                workspace=OPEN_SHELL_WORKSPACE,
            )

            return json.dumps(
                {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.return_code,
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


def delete_sandbox(name: str) -> str:
    """Delete an OpenShell sandbox and release its managed resources."""
    name = _validate_name(name)

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
        raise SandboxError(f"Failed to delete sandbox '{name}'.") from exc
