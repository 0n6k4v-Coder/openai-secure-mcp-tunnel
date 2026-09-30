from __future__ import annotations

import json
import os
import re
import secrets
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


INSTALLATION_STATE_FILE = Path(
    os.environ.get(
        "INSTALLATION_STATE_FILE",
        "/var/lib/local-mcp-server/installations.json",
    )
).resolve()

_INSTALLATION_LOCK = Lock()

_SANDBOX_NAME = re.compile(
    r"^[a-z0-9][a-z0-9-]{0,62}$"
)

_TOOL_NAME = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.+@:/-]{0,127}$"
)

_VERSION = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.+~:@/-]{0,127}$"
)


class InstallationError(RuntimeError):
    """Raised when an installation request is invalid."""


@dataclass(frozen=True)
class InstallationRequest:
    request_id: str
    sandbox_name: str
    tool_name: str
    version: str
    source: str
    install_command: str
    reason: str
    created_at: str


def _ensure_state_directory() -> None:
    INSTALLATION_STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


def _load_state() -> dict[str, dict[str, object]]:
    _ensure_state_directory()

    if not INSTALLATION_STATE_FILE.exists():
        return {}

    try:
        value = json.loads(
            INSTALLATION_STATE_FILE.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise InstallationError(
            "Installation approval state could not be read."
        ) from exc

    if not isinstance(value, dict):
        raise InstallationError(
            "Installation approval state is invalid."
        )

    return value


def _save_state(
    state: dict[str, dict[str, object]],
) -> None:
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

    os.replace(
        temporary,
        INSTALLATION_STATE_FILE,
    )


def _validate_sandbox_name(
    name: str,
) -> str:
    if (
        not isinstance(name, str)
        or not _SANDBOX_NAME.fullmatch(name)
    ):
        raise InstallationError(
            "Invalid sandbox name."
        )

    return name


def _validate_tool_name(
    value: str,
) -> str:
    if (
        not isinstance(value, str)
        or not _TOOL_NAME.fullmatch(value)
    ):
        raise InstallationError(
            "Invalid tool name."
        )

    return value


def _validate_version(
    value: str,
) -> str:
    if (
        not isinstance(value, str)
        or not _VERSION.fullmatch(value)
    ):
        raise InstallationError(
            "Invalid tool version."
        )

    return value


def _validate_source(
    value: str,
) -> str:
    if not isinstance(value, str):
        raise InstallationError(
            "Installation source must be a string."
        )

    source = value.strip()

    if not source:
        raise InstallationError(
            "Installation source must not be empty."
        )

    if len(source) > 2048:
        raise InstallationError(
            "Installation source is too long."
        )

    return source


def _validate_reason(
    value: str,
) -> str:
    if not isinstance(value, str):
        raise InstallationError(
            "Installation reason must be a string."
        )

    reason = value.strip()

    if not reason:
        raise InstallationError(
            "Installation reason must not be empty."
        )

    if len(reason) > 4096:
        raise InstallationError(
            "Installation reason is too long."
        )

    return reason


def _validate_install_command(
    value: str,
) -> str:
    if not isinstance(value, str):
        raise InstallationError(
            "install_command must be a string."
        )

    command = value.strip()

    if not command:
        raise InstallationError(
            "install_command must not be empty."
        )

    if len(command) > 8192:
        raise InstallationError(
            "install_command is too long."
        )

    try:
        tokens = shlex.split(
            command,
            posix=True,
        )
    except ValueError as exc:
        raise InstallationError(
            "install_command has invalid shell quoting."
        ) from exc

    if not tokens:
        raise InstallationError(
            "install_command is empty."
        )

    first = Path(
        tokens[0]
    ).name

    allowed_entrypoints = {
        "apt-get",
        "apt",
        "dnf",
        "yum",
        "apk",
        "pip",
        "pip3",
        "pipx",
        "uv",
        "npm",
        "pnpm",
        "yarn",
        "cargo",
        "go",
        "gem",
        "composer",
        "conda",
    }

    if first not in allowed_entrypoints:
        raise InstallationError(
            "Installation command must start with an approved "
            "package-manager executable."
        )

    shell_metacharacters = {
        "|",
        "||",
        "&",
        "&&",
        ";",
        "`",
        "$(",
        ")",
        ">",
        ">>",
        "<",
        "<<",
    }

    if any(
        token in shell_metacharacters
        for token in tokens
    ):
        raise InstallationError(
            "Shell chaining, redirection, and command substitution "
            "are not permitted in installation commands."
        )

    return command


def create_installation_request(
    *,
    sandbox_name: str,
    tool_name: str,
    version: str,
    source: str,
    install_command: str,
    reason: str,
) -> InstallationRequest:
    request = InstallationRequest(
        request_id=(
            "ins_"
            + secrets.token_urlsafe(18)
        ),
        sandbox_name=_validate_sandbox_name(
            sandbox_name
        ),
        tool_name=_validate_tool_name(
            tool_name
        ),
        version=_validate_version(
            version
        ),
        source=_validate_source(
            source
        ),
        install_command=_validate_install_command(
            install_command
        ),
        reason=_validate_reason(
            reason
        ),
        created_at=datetime.now(
            timezone.utc
        ).isoformat(),
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

        _save_state(
            state
        )

    return request


def approve_installation(
    request_id: str,
) -> InstallationRequest:
    with _INSTALLATION_LOCK:
        state = _load_state()

        entry = state.get(
            request_id
        )

        if entry is None:
            raise InstallationError(
                "Installation request was not found."
            )

        if entry.get("state") != "pending":
            raise InstallationError(
                "Installation request is no longer pending."
            )

        entry["state"] = "approved"

        _save_state(
            state
        )

    return _request_from_state(
        request_id,
        entry,
    )


def deny_installation(
    request_id: str,
) -> None:
    with _INSTALLATION_LOCK:
        state = _load_state()

        entry = state.get(
            request_id
        )

        if entry is None:
            raise InstallationError(
                "Installation request was not found."
            )

        if entry.get("state") != "pending":
            raise InstallationError(
                "Installation request is no longer pending."
            )

        entry["state"] = "denied"

        _save_state(
            state
        )


def consume_installation_approval(
    request_id: str,
) -> InstallationRequest:
    """
    Atomically consume an approval.

    Once consumed, the same approval cannot authorize another installation.
    """
    with _INSTALLATION_LOCK:
        state = _load_state()

        entry = state.get(
            request_id
        )

        if entry is None:
            raise InstallationError(
                "Installation request was not found."
            )

        if entry.get("state") != "approved":
            raise InstallationError(
                "Installation request has not been approved."
            )

        entry["state"] = "consumed"

        _save_state(
            state
        )

    return _request_from_state(
        request_id,
        entry,
    )


def mark_installation_finished(
    request_id: str,
    *,
    success: bool,
) -> None:
    with _INSTALLATION_LOCK:
        state = _load_state()

        entry = state.get(
            request_id
        )

        if entry is None:
            raise InstallationError(
                "Installation request was not found."
            )

        if entry.get("state") != "consumed":
            raise InstallationError(
                "Installation request is not in the consumed state."
            )

        entry["state"] = (
            "completed"
            if success
            else "failed"
        )

        _save_state(
            state
        )


def _request_from_state(
    request_id: str,
    entry: dict[str, object],
) -> InstallationRequest:
    return InstallationRequest(
        request_id=request_id,
        sandbox_name=str(
            entry["sandbox_name"]
        ),
        tool_name=str(
            entry["tool_name"]
        ),
        version=str(
            entry["version"]
        ),
        source=str(
            entry["source"]
        ),
        install_command=str(
            entry["install_command"]
        ),
        reason=str(
            entry["reason"]
        ),
        created_at=str(
            entry["created_at"]
        ),
    )