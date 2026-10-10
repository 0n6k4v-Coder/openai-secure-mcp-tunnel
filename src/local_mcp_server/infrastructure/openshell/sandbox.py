from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import threading
from pathlib import Path

from openshell import SandboxClient

from .client import active_client

from ...sandbox.policy import (
    SANDBOX_WORKSPACE_ROOT,
    build_sandbox_spec,
    validate_command,
    validate_description,
    validate_name,
    validate_profile,
)
from ...workspace.repository import get_workspace_grant


from ...runtime.context import get_runtime_context

_runtime_context = get_runtime_context()
OPENSHELL_WORKSPACE = (
    _runtime_context.profile.openshell_workspace
    if not _runtime_context.is_default
    else os.environ.get("OPENSHELL_WORKSPACE", "default")
)

HOST_WORKSPACE_LABEL = "mcp_host_workspace_id"
SANDBOX_PROFILE_LABEL = "mcp_sandbox_profile"
SANDBOX_DESCRIPTION_LABEL = "mcp_sandbox_description"

_SANDBOX_METADATA_OVERLAY_PATH = Path(
    os.environ.get(
        "SANDBOX_METADATA_OVERLAY_FILE",
        "/var/lib/local-mcp-server/state/sandbox-metadata.json",
    )
)
_overlay_lock = threading.Lock()


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


def _sandbox_description_from_labels(
    labels,
) -> str | None:
    if not isinstance(labels, dict):
        return None

    value = labels.get(SANDBOX_DESCRIPTION_LABEL)

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _sandbox_description_from_overlay(
    name: str,
) -> tuple[bool, str | None]:
    """Read sandbox description from persistent overlay file (hybrid storage)."""
    try:
        overlay_path = _SANDBOX_METADATA_OVERLAY_PATH
        if not overlay_path.exists():
            return False, None
        data = json.loads(overlay_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and name in data and "description" in data[name]:
            return True, data[name]["description"]
    except Exception:
        pass
    return False, None


def _resolve_sandbox_description(
    name: str,
    labels,
) -> str | None:
    """Resolve description: overlay (runtime update) wins over label (create time)."""
    has_overlay, overlay_desc = _sandbox_description_from_overlay(name)
    if has_overlay:
        return overlay_desc
    return _sandbox_description_from_labels(labels)


def update_sandbox_overlay_description(
    name: str,
    description: str | None,
) -> str:
    """Update sandbox description in persistent overlay (hybrid storage)."""
    name = validate_name(name)
    description = validate_description(description)

    # Verify sandbox exists
    sandbox_status(name)

    overlay_path = _SANDBOX_METADATA_OVERLAY_PATH
    with _overlay_lock:
        try:
            overlay_path.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, dict[str, object]] = {}
            if overlay_path.exists():
                try:
                    loaded = json.loads(overlay_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}

            entry = data.setdefault(name, {})
            entry["description"] = description

            tmp_path = overlay_path.with_suffix(f".tmp.{os.getpid()}")
            tmp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(overlay_path)
        except OSError as exc:
            raise SandboxError(
                f"Failed to update sandbox metadata overlay: {exc}"
            ) from exc

    return sandbox_status(name)


def _browser_devtools_readiness(
    sandbox_name: str,
) -> dict[str, object]:
    """Inspect browser sandbox DevTools daemon readiness without starting it."""
    try:
        result = execute_sandbox_argv(
            sandbox_name,
            ["chrome-devtools", "status"],
            timeout_seconds=10,
        )
    except SandboxError as exc:
        return {
            "state": "unavailable",
            "detail": str(exc),
        }

    output = "\n".join(
        value.strip()
        for value in (
            result.get("stdout"),
            result.get("stderr"),
        )
        if isinstance(value, str) and value.strip()
    )

    if int(result.get("return_code", 1)) == 0:
        if "daemon is running" in output.lower():
            return {"state": "ready", "detail": output}
        if "daemon is not running" in output.lower():
            return {"state": "not_ready", "detail": output}

    return {
        "state": "unavailable",
        "detail": output or "Chrome DevTools daemon status is unavailable.",
    }


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
    *,
    include_browser_readiness: bool = False,
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
    description = _resolve_sandbox_description(name or "", labels)

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
        "description": description,
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

    if include_browser_readiness and profile == "browser" and name:
        result["browser"] = {
            "devtools": _browser_devtools_readiness(name),
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
    description: str | None = None,
) -> str:
    """
    Create and wait for an OpenShell sandbox.

    workspace_id is an optional authorized host workspace capability.

    If workspace_id is omitted, the sandbox is standalone and its own
    /workspace/project filesystem is the application workspace.
    """
    name = validate_name(name)
    profile = validate_profile(profile)
    description = validate_description(description)

    grant: dict[str, object] | None = None

    if workspace_id is not None:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("host_workspace_id must not be empty.")

        grant = get_workspace_grant(workspace_id)
        try:
            from ...cli.workspace_broker import ensure_workspace_volume

            ensure_workspace_volume(workspace_id)
        except Exception:
            pass

    labels = {
        SANDBOX_PROFILE_LABEL: profile,
    }

    if description is not None:
        labels[SANDBOX_DESCRIPTION_LABEL] = description

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
                        _sandbox_to_dict(
                            sandbox,
                            include_browser_readiness=True,
                        ),
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
    stdin: bytes | str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, object]:
    name = validate_name(name)

    if not argv:
        raise ValueError("argv must not be empty.")

    if any(not isinstance(argument, str) or "\x00" in argument for argument in argv):
        raise ValueError("argv contains an invalid argument.")

    stdin_bytes: bytes | None = None
    if isinstance(stdin, str):
        stdin_bytes = stdin.encode("utf-8")
    elif isinstance(stdin, (bytes, bytearray)):
        stdin_bytes = bytes(stdin)

    try:
        with _client() as client:
            result = client.exec(
                name,
                argv,
                workspace=OPENSHELL_WORKSPACE,
                timeout_seconds=timeout_seconds,
                no_login_shell=True,
                stdin=stdin_bytes,
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.exit_code,
            }

    except ValueError:
        raise

    except Exception as exc:
        if "sandbox is not ready" in str(exc).lower():
            try:
                start_sandbox(name)
                with _client() as client:
                    result = client.exec(
                        name,
                        argv,
                        workspace=OPENSHELL_WORKSPACE,
                        timeout_seconds=timeout_seconds,
                        no_login_shell=True,
                        stdin=stdin_bytes,
                    )
                    return {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "return_code": result.exit_code,
                    }
            except Exception:
                pass
            from ...mcp.exceptions import SandboxNotReadyError
            raise SandboxNotReadyError(
                name,
                hint=f"It may be stopped. Run 'mcpctl sandbox start {name}' to start it.",
            ) from exc

        raise SandboxError(
            f"Failed to execute argv in sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc


def run_command(
    sandbox_name: str,
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = 120,
    *,
    stdin: bytes | str | None = None,
) -> str:
    """
    Execute a shell command inside an OpenShell sandbox workspace.

    Software installation is deliberately NOT implemented through this
    function. Installation must go through the approval-gated installation
    broker.
    """
    name = validate_name(sandbox_name)
    command = validate_command(command)

    workdir = SANDBOX_WORKSPACE_ROOT
    if cwd is not None:
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError("cwd must not be empty.")
        if "\x00" in cwd:
            raise ValueError("cwd must not contain NUL bytes.")
        clean_cwd = cwd.strip()
        if os.path.isabs(clean_cwd):
            resolved_cwd = os.path.realpath(clean_cwd)
        else:
            resolved_cwd = os.path.realpath(os.path.join(SANDBOX_WORKSPACE_ROOT, clean_cwd))
        if not (resolved_cwd == SANDBOX_WORKSPACE_ROOT or resolved_cwd.startswith(SANDBOX_WORKSPACE_ROOT + "/")):
            raise ValueError(f"cwd '{cwd}' is outside the sandbox workspace.")
        workdir = resolved_cwd

    stdin_bytes: bytes | None = None
    if isinstance(stdin, str):
        stdin_bytes = stdin.encode("utf-8")
    elif isinstance(stdin, (bytes, bytearray)):
        stdin_bytes = bytes(stdin)

    cmd_env = {
        "PAGER": "cat",
        "CI": "1",
        "TERM": "dumb",
        "NO_COLOR": "1",
        "PYTHONUNBUFFERED": "1",
    }

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
                timeout_seconds=timeout_seconds,
                workdir=workdir,
                env=cmd_env,
            )

            return json.dumps(
                {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.exit_code,
                    "cwd": workdir,
                },
                ensure_ascii=False,
                indent=2,
            )

    except ValueError:
        raise

    except Exception as exc:
        if "sandbox is not ready" in str(exc).lower():
            try:
                start_sandbox(name)
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
                        timeout_seconds=timeout_seconds,
                        workdir=workdir,
                        env=cmd_env,
                    )
                    return json.dumps(
                        {
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "return_code": result.exit_code,
                            "cwd": workdir,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
            except Exception:
                pass
            from ...mcp.exceptions import SandboxNotReadyError
            raise SandboxNotReadyError(
                name,
                hint=f"It may be stopped. Run 'mcpctl sandbox start {name}' to start it.",
            ) from exc

        raise SandboxError(
            f"Failed to execute command in sandbox '{name}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def execute_sandbox(
    name: str,
    command: str,
    *,
    stdin: bytes | str | None = None,
) -> str:
    """Internal compatibility helper for execute_sandbox."""
    return run_command(sandbox_name=name, command=command, stdin=stdin)


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

        description = current.get("description")

        # Capture attached credentials before deleting the sandbox
        from .credentials import grant_credential, list_sandbox_credentials
        attached_credentials = []
        try:
            attached_credentials = [
                str(c.get("name"))
                for c in list_sandbox_credentials(name)
                if isinstance(c, dict) and c.get("name")
            ]
        except Exception:
            pass

        delete_sandbox(name)

        created = create_sandbox(
            name=name,
            workspace_id=workspace_id,
            profile=profile,
            description=description,
        )

        # Restore previously granted credentials
        for cred_name in attached_credentials:
            try:
                grant_credential(name, cred_name)
            except Exception:
                pass

        return created

    except SandboxError:
        raise

    except ValueError:
        raise

    except Exception as exc:
        raise SandboxError(
            f"Failed to recreate sandbox '{name}': {type(exc).__name__}: {exc}"
        ) from exc
