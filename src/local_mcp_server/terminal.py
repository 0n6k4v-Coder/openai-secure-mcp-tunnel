from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TOKEN_FILE = Path(
    os.environ.get(
        "TERMINAL_EXECUTOR_TOKEN_FILE",
        "/run/secrets/local_terminal_executor_token",
    )
)

EXECUTOR_URL = os.environ.get(
    "TERMINAL_EXECUTOR_URL",
    "http://terminal-executor:8765",
).rstrip("/")

MAX_COMMAND_BYTES = 32 * 1024
MAX_TIMEOUT_SECONDS = 300


def _load_token() -> str:
    """Load the shared authentication token."""
    token = TOKEN_FILE.read_text(
        encoding="utf-8",
    ).strip()

    if not token:
        raise RuntimeError("Terminal executor token is empty")

    return token


def execute_terminal_command_impl(
    command: str,
    timeout_seconds: int = 30,
) -> str:
    """
    Execute a command through the terminal executor container.

    Commands execute inside the terminal-executor container
    with /workspace as the working directory.
    """
    if not isinstance(command, str):
        raise ValueError("command must be a string")

    if not command.strip():
        raise ValueError("command must not be empty")

    if len(command.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise ValueError(f"command exceeds {MAX_COMMAND_BYTES} bytes")

    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise ValueError("timeout_seconds must be an integer")

    if timeout_seconds < 1 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")

    token = _load_token()

    payload = json.dumps(
        {
            "command": command,
            "timeout_seconds": timeout_seconds,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        url=f"{EXECUTOR_URL}/execute",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds + 10,
        ) as response:
            response_body = response.read().decode(
                "utf-8",
                errors="replace",
            )

    except HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Terminal executor returned HTTP {exc.code}: {error_body}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(f"Could not reach terminal executor: {exc.reason}") from exc

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Terminal executor returned invalid JSON") from exc

    return json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    )
