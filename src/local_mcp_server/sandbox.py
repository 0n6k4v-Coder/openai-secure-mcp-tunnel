from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


OPEN_SHELL_GATEWAY = os.environ.get("OPEN_SHELL_GATEWAY", "")
OPEN_SHELL_WORKSPACE = os.environ.get("OPEN_SHELL_WORKSPACE", "default")
SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE",
    "local-mcp-openshell-sandbox:1.0.0",
)
DEFAULT_CPU = os.environ.get("SANDBOX_DEFAULT_CPU", "1")
DEFAULT_MEMORY = os.environ.get("SANDBOX_DEFAULT_MEMORY", "1GiB")
MAX_COMMAND_BYTES = 32 * 1024
MAX_COMMAND_TIMEOUT = 300

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


def _run_openshell(args: list[str], timeout: int = 60) -> str:
    command = ["openshell"]

    if OPEN_SHELL_GATEWAY:
        command.extend(["--gateway-endpoint", OPEN_SHELL_GATEWAY])

    command.extend(args)

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                "NO_COLOR": "1",
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxError("OpenShell command timed out") from exc
    except OSError as exc:
        raise SandboxError("OpenShell CLI is not available") from exc

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if result.returncode != 0:
        detail = stderr or stdout or "unknown OpenShell error"
        raise SandboxError(
            f"OpenShell command failed with exit code "
            f"{result.returncode}: {detail}"
        )

    return stdout


def create_sandbox(name: str) -> str:
    """Create a policy-enforced OpenShell sandbox."""
    name = _validate_name(name)

    output = _run_openshell(
        [
            "sandbox",
            "create",
            "--name",
            name,
            "--from",
            SANDBOX_IMAGE,
            "--cpu",
            DEFAULT_CPU,
            "--memory",
            DEFAULT_MEMORY,
            "--no-auto-providers",
            "--no-tty",
            "--",
            "sleep",
            "infinity",
        ],
        timeout=120,
    )

    return output or json.dumps(
        {
            "name": name,
            "workspace": OPEN_SHELL_WORKSPACE,
            "image": SANDBOX_IMAGE,
            "status": "created",
        }
    )


def list_sandboxes() -> str:
    """List OpenShell sandboxes in the configured workspace."""
    return _run_openshell(
        [
            "sandbox",
            "list",
            "--output",
            "json",
        ]
    )


def sandbox_status(name: str) -> str:
    """Return OpenShell sandbox metadata."""
    name = _validate_name(name)

    return _run_openshell(
        [
            "sandbox",
            "get",
            name,
            "--output",
            "json",
        ]
    )


def execute_sandbox(
    name: str,
    command: str,
    timeout_seconds: int = 30,
) -> str:
    """Execute a command inside an existing OpenShell sandbox."""
    name = _validate_name(name)
    command = _validate_command(command)

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds < 1
        or timeout_seconds > MAX_COMMAND_TIMEOUT
    ):
        raise ValueError(
            f"timeout_seconds must be an integer between 1 and "
            f"{MAX_COMMAND_TIMEOUT}"
        )

    return _run_openshell(
        [
            "sandbox",
            "exec",
            "--name",
            name,
            "--no-tty",
            "--no-login-shell",
            "--timeout",
            str(timeout_seconds),
            "--",
            "sh",
            "-lc",
            command,
        ],
        timeout=timeout_seconds + 30,
    )


def delete_sandbox(name: str) -> str:
    """Delete an OpenShell sandbox and release its managed resources."""
    name = _validate_name(name)

    return _run_openshell(
        [
            "sandbox",
            "delete",
            name,
        ],
        timeout=120,
    )
