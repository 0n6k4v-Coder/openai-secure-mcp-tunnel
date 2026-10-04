from __future__ import annotations

import json
import re

from ..infrastructure.openshell.sandbox import (
    SandboxError,
    execute_sandbox_argv,
    sandbox_status,
)
from ..sandbox.policy import validate_name


_BROWSER_URL = "http://127.0.0.1:9222"
_COMMAND_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

_MAX_ARGUMENTS = 64
_MAX_OUTPUT_BYTES = 1024 * 1024

_FORBIDDEN_CONNECTION_FLAGS = frozenset(
    {
        "-u",
        "--browserUrl",
        "--browser-url",
        "-w",
        "--wsEndpoint",
        "--ws-endpoint",
        "--wsHeaders",
        "--ws-headers",
        "-e",
        "--executablePath",
        "--executable-path",
        "--channel",
        "--userDataDir",
        "--user-data-dir",
    }
)

_FORBIDDEN_LIFECYCLE_COMMANDS = frozenset({"start", "stop", "status"})


class ChromeDevToolsError(RuntimeError):
    """Raised when a Chrome DevTools operation fails."""


def _validate_command(command: str) -> str:
    if not isinstance(command, str) or not _COMMAND_NAME.fullmatch(command):
        raise ChromeDevToolsError(
            "Chrome DevTools command must contain only lowercase letters, "
            "digits, and underscores and must start with a letter."
        )

    if command in _FORBIDDEN_LIFECYCLE_COMMANDS:
        raise ChromeDevToolsError(
            f"Chrome DevTools lifecycle command '{command}' is not available. "
            "The browser runtime lifecycle is managed by the browser sandbox."
        )

    return command


def _validate_arguments(
    arguments: list[str] | None,
) -> list[str]:
    values = list(arguments or [])

    if len(values) > _MAX_ARGUMENTS:
        raise ChromeDevToolsError(
            f"Chrome DevTools accepts at most {_MAX_ARGUMENTS} arguments."
        )

    for index, argument in enumerate(values):
        if not isinstance(argument, str) or "\x00" in argument:
            raise ChromeDevToolsError("Chrome DevTools arguments contain invalid data.")

        token = argument.split("=", 1)[0]

        if token in _FORBIDDEN_CONNECTION_FLAGS:
            raise ChromeDevToolsError(
                "Chrome DevTools connection flags cannot be overridden; "
                f"the browser endpoint is fixed to {_BROWSER_URL}."
            )

        if index > 0 and values[index - 1] in _FORBIDDEN_CONNECTION_FLAGS:
            raise ChromeDevToolsError(
                "Chrome DevTools connection flags cannot be overridden; "
                f"the browser endpoint is fixed to {_BROWSER_URL}."
            )

    return values


def _validate_browser_sandbox(sandbox_name: str) -> None:
    status = json.loads(sandbox_status(sandbox_name))

    if status.get("profile") != "browser":
        raise ChromeDevToolsError(
            f"Sandbox '{sandbox_name}' is not a browser sandbox. "
            "Create or select a sandbox with profile='browser'."
        )


def _bounded_result(
    result: dict[str, object],
) -> dict[str, object]:
    bounded = dict(result)

    for key in ("stdout", "stderr"):
        value = bounded.get(key)

        if isinstance(value, str):
            encoded = value.encode("utf-8")

            if len(encoded) > _MAX_OUTPUT_BYTES:
                bounded[key] = (
                    encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
                    + "\n[output truncated]"
                )

    bounded["browser_url"] = _BROWSER_URL

    return bounded


def execute_chrome_devtools(
    *,
    sandbox_name: str,
    command: str,
    arguments: list[str] | None = None,
) -> dict[str, object]:
    """Execute a Chrome DevTools CLI command in an existing browser sandbox."""
    sandbox_name = validate_name(sandbox_name)
    command = _validate_command(command)
    arguments = _validate_arguments(arguments)

    try:
        _validate_browser_sandbox(sandbox_name)

        result = execute_sandbox_argv(
            sandbox_name,
            [
                "chrome-devtools",
                command,
                *arguments,
            ],
            timeout_seconds=120,
        )

        bounded = _bounded_result(result)

        if int(bounded["return_code"]) != 0:
            raise ChromeDevToolsError(
                "chrome-devtools failed with exit code "
                f"{bounded['return_code']}: "
                f"{bounded.get('stderr') or bounded.get('stdout')}"
            )

        bounded["sandbox_name"] = sandbox_name
        return bounded

    except json.JSONDecodeError as exc:
        raise ChromeDevToolsError(
            f"Chrome DevTools received invalid sandbox status: {exc}"
        ) from exc

    except (ValueError, ChromeDevToolsError):
        raise

    except SandboxError as exc:
        raise ChromeDevToolsError(
            f"Chrome DevTools sandbox operation failed: {exc}"
        ) from exc

    except TypeError as exc:
        raise ChromeDevToolsError(
            f"Chrome DevTools received invalid sandbox status: {exc}"
        ) from exc

    except Exception as exc:
        raise ChromeDevToolsError(
            f"Chrome DevTools execution failed: {type(exc).__name__}: {exc}"
        ) from exc
