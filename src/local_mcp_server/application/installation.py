from __future__ import annotations

import json
import os
import re
import secrets
import shlex
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Final

from ..domain.installation import InstallationRequest
from ..infrastructure.openshell.client import active_client
from ..infrastructure.openshell.sandbox import OPENSHELL_WORKSPACE


INSTALLATION_STATE_FILE = Path(
    os.environ.get(
        "INSTALLATION_STATE_FILE",
        "/var/lib/local-mcp-server/installations.json",
    )
).resolve()

INSTALLATION_TIMEOUT_SECONDS: Final[int] = int(
    os.environ.get("INSTALLATION_TIMEOUT_SECONDS", "300")
)

_INSTALLATION_LOCK = Lock()

_SANDBOX_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+@:/-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+~:@/=<>,!* -]{0,127}$")

_ALLOWED_ENTRYPOINTS: Final = frozenset(
    {
        "apt", "apt-get", "apk", "cargo", "conda", "composer", "dnf",
        "gem", "go", "npm", "pip", "pip3", "pipx", "pnpm", "uv",
        "yarn", "yum",
    }
)

_FORBIDDEN_SHELL_CHARS: Final = frozenset(
    {"\x00", "\n", "\r", ";", "|", "&", ">", "<", "`", "$"}
)


class InstallationError(RuntimeError):
    """Raised when an installation request is invalid or fails."""


def _ensure_state_directory() -> None:
    INSTALLATION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict[str, dict[str, object]]:
    _ensure_state_directory()
    if not INSTALLATION_STATE_FILE.exists():
        return {}

    try:
        value = json.loads(
            INSTALLATION_STATE_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallationError(
            "Installation approval state could not be read."
        ) from exc

    if not isinstance(value, dict):
        raise InstallationError("Installation approval state is invalid.")

    return value


def _save_state(state: dict[str, dict[str, object]]) -> None:
    _ensure_state_directory()
    temporary = INSTALLATION_STATE_FILE.with_suffix(
        INSTALLATION_STATE_FILE.suffix + ".tmp"
    )
    temporary.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, INSTALLATION_STATE_FILE)


def _validate_sandbox_name(name: str) -> str:
    if not isinstance(name, str) or not _SANDBOX_NAME.fullmatch(name):
        raise InstallationError("Invalid sandbox name.")
    return name


def _validate_tool_name(value: str) -> str:
    if not isinstance(value, str) or not _TOOL_NAME.fullmatch(value):
        raise InstallationError("Invalid tool name.")
    return value


def _validate_version(value: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise InstallationError("Invalid tool version.")
    return value


def _validate_source(value: str) -> str:
    if not isinstance(value, str):
        raise InstallationError("Installation source must be a string.")
    source = value.strip()
    if not source:
        raise InstallationError("Installation source must not be empty.")
    if len(source) > 2048:
        raise InstallationError("Installation source is too long.")
    return source


def _validate_reason(value: str) -> str:
    if not isinstance(value, str):
        raise InstallationError("Installation reason must be a string.")
    reason = value.strip()
    if not reason:
        raise InstallationError("Installation reason must not be empty.")
    if len(reason) > 4096:
        raise InstallationError("Installation reason is too long.")
    return reason


def _validate_timeout() -> int:
    if not 1 <= INSTALLATION_TIMEOUT_SECONDS <= 3600:
        raise InstallationError(
            "INSTALLATION_TIMEOUT_SECONDS must be between 1 and 3600."
        )
    return INSTALLATION_TIMEOUT_SECONDS


def _validate_install_command(value: str) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise InstallationError("install_command must be a string.")

    command = value.strip()
    if not command:
        raise InstallationError("install_command must not be empty.")
    if len(command) > 8192:
        raise InstallationError("install_command is too long.")
    if any(char in command for char in _FORBIDDEN_SHELL_CHARS):
        raise InstallationError(
            "install_command contains forbidden shell syntax."
        )

    try:
        tokens = tuple(shlex.split(command, posix=True))
    except ValueError as exc:
        raise InstallationError(
            "install_command has invalid shell quoting."
        ) from exc

    if not tokens:
        raise InstallationError("install_command is empty.")

    executable = tokens[0]
    if executable not in _ALLOWED_ENTRYPOINTS:
        raise InstallationError(
            "Installation command must start with an approved "
            "package-manager executable."
        )

    operations = set(tokens[1:])

    if executable in {"apt", "apt-get", "dnf", "yum"} and "install" not in operations:
        raise InstallationError(
            "System package installation commands must use install."
        )
    if executable == "apk" and "add" not in operations:
        raise InstallationError("apk installation commands must use add.")
    if executable in {"pip", "pip3", "pipx"} and "install" not in operations:
        raise InstallationError(
            "Python package installation commands must use install."
        )
    if executable == "uv":
        if len(tokens) < 3 or tuple(tokens[1:3]) not in {
            ("tool", "install"),
            ("pip", "install"),
        }:
            raise InstallationError(
                "uv installation commands must use 'uv tool install' "
                "or 'uv pip install'."
            )
    if executable == "npm" and not {"install", "add"} & operations:
        raise InstallationError(
            "npm installation commands must use install or add."
        )
    if executable in {"pnpm", "yarn"} and not {"install", "add"} & operations:
        raise InstallationError(
            "Node package installation commands must use install or add."
        )
    if executable in {"cargo", "go", "gem"} and "install" not in operations:
        raise InstallationError(
            f"{executable} installation commands must use install."
        )
    if executable == "composer" and "require" not in operations:
        raise InstallationError(
            "Composer installation commands must use require."
        )
    if executable == "conda" and not {"install", "create"} & operations:
        raise InstallationError(
            "Conda installation commands must use install or create."
        )

    return tokens


def create_installation_request(
    *,
    sandbox_name: str,
    tool_name: str,
    version: str,
    source: str,
    install_command: str,
    reason: str,
) -> InstallationRequest:
    _validate_timeout()
    tokens = _validate_install_command(install_command)

    request = InstallationRequest(
        request_id="ins_" + secrets.token_urlsafe(18),
        sandbox_name=_validate_sandbox_name(sandbox_name),
        tool_name=_validate_tool_name(tool_name),
        version=_validate_version(version),
        source=_validate_source(source),
        install_command=shlex.join(tokens),
        reason=_validate_reason(reason),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    with _INSTALLATION_LOCK:
        state = _load_state()
        state[request.request_id] = {
            "sandbox_name": request.sandbox_name,
            "tool_name": request.tool_name,
            "version": request.version,
            "source": request.source,
            "install_command": request.install_command,
            "reason": request.reason,
            "created_at": request.created_at,
            "state": "pending",
        }
        _save_state(state)

    return request


def approve_installation(request_id: str) -> InstallationRequest:
    with _INSTALLATION_LOCK:
        state = _load_state()
        entry = state.get(request_id)
        if entry is None:
            raise InstallationError("Installation request was not found.")
        if entry.get("state") != "pending":
            raise InstallationError(
                "Installation request is no longer pending."
            )
        entry["state"] = "approved"
        entry["approved_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)

    return _request_from_state(request_id, entry)


def deny_installation(request_id: str) -> None:
    with _INSTALLATION_LOCK:
        state = _load_state()
        entry = state.get(request_id)
        if entry is None:
            raise InstallationError("Installation request was not found.")
        if entry.get("state") != "pending":
            raise InstallationError(
                "Installation request is no longer pending."
            )
        entry["state"] = "denied"
        entry["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)


def consume_installation_approval(
    request_id: str,
) -> InstallationRequest:
    with _INSTALLATION_LOCK:
        state = _load_state()
        entry = state.get(request_id)
        if entry is None:
            raise InstallationError("Installation request was not found.")
        if entry.get("state") != "approved":
            raise InstallationError(
                "Installation request has not been approved."
            )
        entry["state"] = "consumed"
        entry["consumed_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)

    return _request_from_state(request_id, entry)


def mark_installation_finished(
    request_id: str,
    *,
    success: bool,
) -> None:
    with _INSTALLATION_LOCK:
        state = _load_state()
        entry = state.get(request_id)
        if entry is None:
            raise InstallationError("Installation request was not found.")
        if entry.get("state") != "consumed":
            raise InstallationError(
                "Installation request is not in the consumed state."
            )
        entry["state"] = "completed" if success else "failed"
        entry["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)


def execute_installation(
    request: InstallationRequest,
) -> dict[str, object]:
    consumed = consume_installation_approval(request.request_id)

    try:
        tokens = _validate_install_command(consumed.install_command)

        with active_client() as client:
            result = client.exec(
                consumed.sandbox_name,
                list(tokens),
                workspace=OPENSHELL_WORKSPACE,
                timeout_seconds=_validate_timeout(),
                no_login_shell=True,
            )

        success = result.exit_code == 0
        mark_installation_finished(
            consumed.request_id,
            success=success,
        )

        return {
            "request_id": consumed.request_id,
            "sandbox_name": consumed.sandbox_name,
            "tool_name": consumed.tool_name,
            "version": consumed.version,
            "source": consumed.source,
            "install_command": consumed.install_command,
            "approved": True,
            "executed": True,
            "success": success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.exit_code,
        }
    except Exception as exc:
        try:
            mark_installation_finished(
                consumed.request_id,
                success=False,
            )
        except InstallationError:
            pass

        raise InstallationError(
            f"Installation failed in sandbox "
            f"'{consumed.sandbox_name}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _request_from_state(
    request_id: str,
    entry: dict[str, object],
) -> InstallationRequest:
    required = (
        "sandbox_name",
        "tool_name",
        "version",
        "source",
        "install_command",
        "reason",
        "created_at",
    )
    missing = [field for field in required if field not in entry]
    if missing:
        raise InstallationError(
            "Installation state is missing fields: " + ", ".join(missing)
        )

    return InstallationRequest(
        request_id=request_id,
        sandbox_name=str(entry["sandbox_name"]),
        tool_name=str(entry["tool_name"]),
        version=str(entry["version"]),
        source=str(entry["source"]),
        install_command=str(entry["install_command"]),
        reason=str(entry["reason"]),
        created_at=str(entry["created_at"]),
    )
