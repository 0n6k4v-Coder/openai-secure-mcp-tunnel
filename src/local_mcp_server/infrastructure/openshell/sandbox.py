from __future__ import annotations

import json
import os
import shutil
import subprocess

from openshell import SandboxClient

from .client import active_client

from ...sandbox.policy import (
    SANDBOX_WORKSPACE_ROOT,
    build_sandbox_spec,
    validate_command,
    validate_name,
    validate_profile,
)
from ...workspace.repository import get_workspace_grant


OPENSHELL_WORKSPACE = "default"

HOST_WORKSPACE_LABEL = "mcp_host_workspace_id"
SANDBOX_PROFILE_LABEL = "mcp_sandbox_profile"


class SandboxError(RuntimeError):
    """Raised when an OpenShell sandbox operation fails."""


def _client() -> SandboxClient:
    try:
        return active_client()

    except Exception as exc:
        raise SandboxError(
            f"Could not connect to the configured OpenShell gateway: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _openshell_command(*args: str) -> list[str]:
    executable = shutil.which("openshell")

    if executable is None:
        raise SandboxError(
            "The OpenShell CLI is not installed in the MCP server runtime."
        )

    return [executable, *args]


def _run_openshell_output(
    *args: str,
    timeout_seconds: int = 30,
) -> str:
    environment = {
        **os.environ,
        "OPENSHELL_WORKSPACE": OPENSHELL_WORKSPACE,
    }

    try:
        completed = subprocess.run(
            _openshell_command(*args),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )

    except subprocess.TimeoutExpired as exc:
        raise SandboxError(
            f"OpenShell output command timed out: {' '.join(args)}"
        ) from exc

    except OSError as exc:
        raise SandboxError(
            f"Failed to execute OpenShell output command: {type(exc).__name__}: {exc}"
        ) from exc

    if completed.returncode != 0:
        diagnostic = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "OpenShell returned no diagnostic output."
        )

        raise SandboxError(
            f"OpenShell command failed with exit code "
            f"{completed.returncode}: {diagnostic}"
        )

    return completed.stdout


def _host_workspace_id_from_labels(
    labels,
) -> str | None:
    if not isinstance(labels, dict):
        return None

    value = labels.get(HOST_WORKSPACE_LABEL)

    if isinstance(value, str) and value:
        return value

    return None


def _sandbox_profile_from_labels(
    labels,
) -> str:
    if not isinstance(labels, dict):
        return "default"

    value = labels.get(SANDBOX_PROFILE_LABEL)

    if value in {"default", "browser"}:
        return value

    return "default"


def _host_workspace_metadata(
    host_workspace_id: str | None,
) -> dict[str, object] | None:
    if not host_workspace_id:
        return None

    try:
        grant = get_workspace_grant(host_workspace_id)
    except ValueError:
        return {
            "type": "host",
            "id": host_workspace_id,
            "authorized": False,
        }

    return {
        "type": "host",
        "id": host_workspace_id,
        "authorized": True,
        "root": grant["target"],
        "read_only": grant["read_only"],
    }


def _sandbox_workspace_metadata(
    sandbox_name: str,
) -> dict[str, object]:
    return {
        "type": "sandbox",
        "id": sandbox_name,
        "authorized": True,
        "root": SANDBOX_WORKSPACE_ROOT,
        "read_only": False,
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

    name = getattr(
        sandbox,
        "name",
        None,
    )

    host_workspace_id = _host_workspace_id_from_labels(labels)
    profile = _sandbox_profile_from_labels(labels)

    if host_workspace_id:
        workspace = _host_workspace_metadata(host_workspace_id)

        if workspace is None:
            workspace = _sandbox_workspace_metadata(name or "")
    else:
        workspace = _sandbox_workspace_metadata(name or "")

    result: dict[str, object] = {
        "id": getattr(
            sandbox,
            "id",
            None,
        ),
        "name": name,
        "openshell_workspace": OPENSHELL_WORKSPACE,
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
        "profile": profile,
        "workspace": workspace,
        "labels": labels,
    }

    if host_workspace_id:
        result["host_workspace_id"] = host_workspace_id

        metadata = _host_workspace_metadata(host_workspace_id)

        if metadata is not None:
            result["host_workspace"] = metadata

    return result


def create_sandbox(
    name: str,
    workspace_id: str | None = None,
    profile: str = "default",
) -> str:
    """
    Create and wait for an OpenShell sandbox.

    workspace_id is an optional authorized host workspace capability.

    If workspace_id is omitted, the sandbox is standalone and its own
    /workspace/project filesystem is the application workspace.
    """
    name = validate_name(name)
    profile = validate_profile(profile)

    grant: dict[str, object] | None = None

    if workspace_id is not None:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("host_workspace_id must not be empty.")

        grant = get_workspace_grant(workspace_id)

    labels = {
        SANDBOX_PROFILE_LABEL: profile,
    }

    if workspace_id is not None:
        labels[HOST_WORKSPACE_LABEL] = workspace_id

    try:
        with _client() as client:
            sandbox = client.create(
                workspace=OPENSHELL_WORKSPACE,
                name=name,
                labels=labels,
                spec=build_sandbox_spec(
                    workspace_id,
                    profile=profile,
                ),
            )

            ready = client.wait_ready(
                sandbox.name,
                workspace=OPENSHELL_WORKSPACE,
                timeout_seconds=120,
            )

            result = _sandbox_to_dict(ready)

            if workspace_id is not None and grant is not None:
                result["host_workspace_id"] = workspace_id
                result["host_workspace"] = {
                    "type": "host",
                    "id": workspace_id,
                    "authorized": True,
                    "root": grant["target"],
                    "read_only": grant["read_only"],
                }

            else:
                result["workspace"] = _sandbox_workspace_metadata(
                    sandbox.name,
                )

            return json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to create sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc


def list_sandboxes() -> str:
    try:
        with _client() as client:
            sandboxes = client.list_all(
                workspace=OPENSHELL_WORKSPACE,
            )

            return json.dumps(
                [_sandbox_to_dict(sandbox) for sandbox in sandboxes],
                ensure_ascii=False,
                indent=2,
            )

    except Exception as exc:
        raise SandboxError(
            f"Failed to list OpenShell sandboxes: {type(exc).__name__}: {exc}"
        ) from exc


def sandbox_status(
    name: str,
) -> str:
    name = validate_name(name)

    try:
        with _client() as client:
            sandboxes = client.list_all(
                workspace=OPENSHELL_WORKSPACE,
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
        raise SandboxError(
            f"Failed to inspect sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc

    raise SandboxError(f"Sandbox '{name}' was not found.")


def start_sandbox(
    name: str,
) -> str:
    name = validate_name(name)

    try:
        with _client() as client:
            started = client.start(
                name,
                workspace=OPENSHELL_WORKSPACE,
            )

            return json.dumps(
                _sandbox_to_dict(started),
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to start sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc


def stop_sandbox(
    name: str,
) -> str:
    name = validate_name(name)

    try:
        with _client() as client:
            stopped = client.stop(
                name,
                workspace=OPENSHELL_WORKSPACE,
            )

            return json.dumps(
                _sandbox_to_dict(stopped),
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to stop sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc


def restart_sandbox(
    name: str,
) -> str:
    name = validate_name(name)

    stop_sandbox(name)

    return start_sandbox(name)


def repair_sandbox(
    name: str,
) -> str:
    name = validate_name(name)

    return start_sandbox(name)


def sandbox_logs(
    name: str,
    *,
    since: str = "5m",
) -> str:
    name = validate_name(name)

    if not isinstance(since, str) or not since.strip():
        raise ValueError("since must not be empty.")

    return _run_openshell_output(
        "logs",
        name,
        "--since",
        since,
    )


def execute_sandbox_argv(
    name: str,
    argv: list[str],
    *,
    timeout_seconds: int = 120,
) -> dict[str, object]:
    name = validate_name(name)

    if not argv:
        raise ValueError("argv must not be empty.")

    if any(not isinstance(argument, str) or "\x00" in argument for argument in argv):
        raise ValueError("argv contains an invalid argument.")

    try:
        with _client() as client:
            result = client.exec(
                name,
                argv,
                workspace=OPENSHELL_WORKSPACE,
                timeout_seconds=timeout_seconds,
                no_login_shell=True,
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.exit_code,
            }

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to execute argv in sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc


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
    name = validate_name(name)

    command = validate_command(command)

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
                workspace=OPENSHELL_WORKSPACE,
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
    name = validate_name(name)

    try:
        with _client() as client:
            deletion = client.delete(
                name,
                workspace=OPENSHELL_WORKSPACE,
            )

            client.wait_deleted(
                name,
                workspace=OPENSHELL_WORKSPACE,
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
            f"Failed to delete sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc


def recreate_sandbox(
    name: str,
) -> str:
    """
    Delete and recreate a sandbox while preserving its profile and workspace
    binding.

    A host-backed sandbox preserves its host workspace capability.

    A standalone sandbox is recreated without a host workspace, so its new
    sandbox-local filesystem becomes its workspace.
    """
    name = validate_name(name)

    try:
        current = json.loads(
            sandbox_status(name),
        )

        if not isinstance(current, dict):
            raise SandboxError(f"Sandbox '{name}' returned invalid metadata.")

        workspace_id = current.get(
            "host_workspace_id",
        )

        if workspace_id is not None:
            if not isinstance(workspace_id, str) or not workspace_id:
                raise SandboxError(
                    f"Sandbox '{name}' contains an invalid host workspace ID."
                )

        profile = current.get(
            "profile",
            "default",
        )

        if profile not in {"default", "browser"}:
            raise SandboxError(f"Sandbox '{name}' has unsupported profile '{profile}'.")

        delete_sandbox(name)

        return create_sandbox(
            name=name,
            workspace_id=workspace_id,
            profile=profile,
        )

    except SandboxError:
        raise

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to recreate sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc
