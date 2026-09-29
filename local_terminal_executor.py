from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import platform
import secrets
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = os.environ.get("LOCAL_TERMINAL_EXECUTOR_HOST", "0.0.0.0")
PORT = int(os.environ.get("LOCAL_TERMINAL_EXECUTOR_PORT", "8765"))

TOKEN_FILE = Path(
    os.environ.get(
        "LOCAL_TERMINAL_EXECUTOR_TOKEN_FILE",
        ".secrets/local-terminal-executor-token",
    )
)

MAX_COMMAND_BYTES = 32 * 1024
MAX_TIMEOUT_SECONDS = 300
MAX_OUTPUT_BYTES = 1_000_000

logger = logging.getLogger("local_terminal_executor")


def load_token() -> str:
    """Load the executor bearer token from disk."""
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    if not token:
        raise RuntimeError(f"Token file is empty: {TOKEN_FILE}")

    if len(token) < 32:
        raise RuntimeError("Executor token is unexpectedly short")

    return token


EXECUTOR_TOKEN = load_token()


def json_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict,
) -> None:
    """Send a JSON HTTP response."""
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def authenticate(handler: BaseHTTPRequestHandler) -> bool:
    """Authenticate an incoming request using a bearer token."""
    authorization = handler.headers.get("Authorization", "")

    expected = f"Bearer {EXECUTOR_TOKEN}"

    if not hmac.compare_digest(authorization, expected):
        json_response(
            handler,
            HTTPStatus.UNAUTHORIZED,
            {
                "error": "unauthorized",
            },
        )
        return False

    return True


def read_json_body(
    handler: BaseHTTPRequestHandler,
) -> dict:
    """Read and decode a bounded JSON request body."""
    content_length_header = handler.headers.get("Content-Length")

    if content_length_header is None:
        raise ValueError("Missing Content-Length")

    try:
        content_length = int(content_length_header)
    except ValueError as exc:
        raise ValueError("Invalid Content-Length") from exc

    if content_length < 0 or content_length > MAX_COMMAND_BYTES + 8192:
        raise ValueError("Request body is too large")

    body = handler.rfile.read(content_length)

    if len(body) != content_length:
        raise ValueError("Incomplete request body")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Request body must contain valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")

    return payload


def validate_command(command: object) -> str:
    """Validate the requested shell command."""
    if not isinstance(command, str):
        raise ValueError("command must be a string")

    if not command.strip():
        raise ValueError("command must not be empty")

    command_bytes = command.encode("utf-8")

    if len(command_bytes) > MAX_COMMAND_BYTES:
        raise ValueError(
            f"command exceeds {MAX_COMMAND_BYTES} bytes"
        )

    return command


def validate_timeout(timeout: object) -> int:
    """Validate the requested command timeout."""
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        raise ValueError("timeout_seconds must be an integer")

    if timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be between 1 and "
            f"{MAX_TIMEOUT_SECONDS}"
        )

    return timeout


def execute_command(
    command: str,
    timeout_seconds: int,
) -> dict:
    """
    Execute a command using the host operating system shell.

    This process intentionally runs outside Docker so that the command
    executes on the user's actual host machine.
    """
    command_hash = hashlib.sha256(
        command.encode("utf-8")
    ).hexdigest()

    logger.info(
        "Executing host terminal command "
        "command_sha256=%s "
        "timeout_seconds=%d "
        "platform=%s",
        command_hash,
        timeout_seconds,
        platform.platform(),
    )

    process = subprocess.Popen(
        command,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        process.kill()

        stdout, stderr = process.communicate()

        return {
            "ok": False,
            "timed_out": True,
            "return_code": None,
            "stdout": stdout[:MAX_OUTPUT_BYTES].decode(
                "utf-8",
                errors="replace",
            ),
            "stderr": stderr[:MAX_OUTPUT_BYTES].decode(
                "utf-8",
                errors="replace",
            ),
            "command_sha256": command_hash,
            "timeout_seconds": timeout_seconds,
        }

    stdout_truncated = len(stdout) > MAX_OUTPUT_BYTES
    stderr_truncated = len(stderr) > MAX_OUTPUT_BYTES

    return {
        "ok": process.returncode == 0,
        "timed_out": False,
        "return_code": process.returncode,
        "stdout": stdout[:MAX_OUTPUT_BYTES].decode(
            "utf-8",
            errors="replace",
        ),
        "stderr": stderr[:MAX_OUTPUT_BYTES].decode(
            "utf-8",
            errors="replace",
        ),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "command_sha256": command_hash,
        "timeout_seconds": timeout_seconds,
    }


class ExecutorHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local terminal executor."""

    server_version = "LocalTerminalExecutor/0.1"

    def log_message(self, format: str, *args) -> None:
        logger.info(
            "HTTP %s",
            format % args,
        )

    def do_GET(self) -> None:
        if self.path == "/healthz":
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "local-terminal-executor",
                },
            )
            return

        json_response(
            self,
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
            },
        )

    def do_POST(self) -> None:
        if self.path != "/execute":
            json_response(
                self,
                HTTPStatus.NOT_FOUND,
                {
                    "error": "not_found",
                },
            )
            return

        if not authenticate(self):
            return

        try:
            payload = read_json_body(self)

            command = validate_command(
                payload.get("command"),
            )

            timeout_seconds = validate_timeout(
                payload.get("timeout_seconds", 30),
            )

            result = execute_command(
                command,
                timeout_seconds,
            )

        except ValueError as exc:
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "error": str(exc),
                },
            )
            return

        except Exception:
            logger.exception(
                "Unexpected terminal executor failure"
            )

            json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "internal_server_error",
                },
            )
            return

        json_response(
            self,
            HTTPStatus.OK,
            result,
        )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )

    logger.info(
        "Starting local terminal executor "
        "host=%s port=%d token_file=%s "
        "platform=%s",
        HOST,
        PORT,
        TOKEN_FILE,
        platform.platform(),
    )

    server = ThreadingHTTPServer(
        (HOST, PORT),
        ExecutorHandler,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
