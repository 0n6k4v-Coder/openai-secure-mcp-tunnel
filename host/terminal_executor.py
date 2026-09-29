from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


HOST = os.environ.get(
    "LOCAL_TERMINAL_EXECUTOR_HOST",
    "0.0.0.0",
)

PORT = int(
    os.environ.get(
        "LOCAL_TERMINAL_EXECUTOR_PORT",
        "8765",
    )
)

TOKEN_FILE = Path(
    os.environ.get(
        "LOCAL_TERMINAL_EXECUTOR_TOKEN_FILE",
        "/run/secrets/local_terminal_executor_token",
    )
)

MAX_COMMAND_LENGTH = 32 * 1024
MAX_TIMEOUT_SECONDS = 300
MAX_OUTPUT_BYTES = 1024 * 1024

LOGGER = logging.getLogger(
    "local-terminal-executor"
)


def load_token() -> str:
    """Load the shared authentication token."""
    try:
        token = TOKEN_FILE.read_text(
            encoding="utf-8",
        ).strip()
    except OSError as exc:
        raise RuntimeError(
            f"Unable to read terminal executor token "
            f"from {TOKEN_FILE}: {exc}"
        ) from exc

    if len(token) < 32:
        raise RuntimeError(
            "Terminal executor token must contain "
            "at least 32 characters."
        )

    return token


TOKEN = load_token()


def command_hash(command: str) -> str:
    """Return a stable SHA-256 identifier."""
    return hashlib.sha256(
        command.encode("utf-8")
    ).hexdigest()


def truncate_output(
    data: bytes,
) -> tuple[str, bool]:
    """Decode output and enforce the maximum size."""
    truncated = len(data) > MAX_OUTPUT_BYTES

    if truncated:
        data = data[:MAX_OUTPUT_BYTES]

    return (
        data.decode(
            "utf-8",
            errors="replace",
        ),
        truncated,
    )


def json_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
) -> None:
    """Write a JSON HTTP response."""
    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    handler.send_response(status)

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8",
    )

    handler.send_header(
        "Content-Length",
        str(len(body)),
    )

    handler.send_header(
        "Cache-Control",
        "no-store",
    )

    handler.end_headers()

    handler.wfile.write(body)


class TerminalExecutorHandler(
    BaseHTTPRequestHandler
):
    """Authenticated terminal execution HTTP handler."""

    server_version = (
        "LocalTerminalExecutor/1.0"
    )

    def log_message(
        self,
        format: str,
        *args: Any,
    ) -> None:
        """Use application logging."""
        LOGGER.info(
            "http_request",
            extra={
                "message": format % args,
            },
        )

    def do_GET(self) -> None:
        if self.path == "/healthz":
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": (
                        "local-terminal-executor"
                    ),
                },
            )
            return

        json_response(
            self,
            HTTPStatus.NOT_FOUND,
            {
                "ok": False,
                "error": "not_found",
            },
        )

    def do_POST(self) -> None:
        if self.path != "/execute":
            json_response(
                self,
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "not_found",
                },
            )
            return

        if not self._authenticate():
            return

        try:
            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )
        except ValueError:
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": (
                        "invalid_content_length"
                    ),
                },
            )
            return

        if content_length <= 0:
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": (
                        "request_body_required"
                    ),
                },
            )
            return

        if (
            content_length
            > MAX_COMMAND_LENGTH + 8192
        ):
            json_response(
                self,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {
                    "ok": False,
                    "error": (
                        "request_body_too_large"
                    ),
                },
            )
            return

        body = self.rfile.read(
            content_length
        )

        try:
            payload = json.loads(
                body.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "invalid_json",
                },
            )
            return

        if not isinstance(
            payload,
            dict,
        ):
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": (
                        "request_body_must_be_object"
                    ),
                },
            )
            return

        command = payload.get(
            "command"
        )

        timeout_seconds = payload.get(
            "timeout_seconds",
            30,
        )

        if not isinstance(
            command,
            str,
        ):
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": (
                        "command_must_be_string"
                    ),
                },
            )
            return

        if not command.strip():
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": (
                        "command_must_not_be_empty"
                    ),
                },
            )
            return

        if len(command) > MAX_COMMAND_LENGTH:
            json_response(
                self,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {
                    "ok": False,
                    "error": "command_too_long",
                    "max_command_length": (
                        MAX_COMMAND_LENGTH
                    ),
                },
            )
            return

        if (
            isinstance(
                timeout_seconds,
                bool,
            )
            or not isinstance(
                timeout_seconds,
                int,
            )
        ):
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": (
                        "timeout_seconds_must_be_integer"
                    ),
                },
            )
            return

        if (
            timeout_seconds < 1
            or timeout_seconds
            > MAX_TIMEOUT_SECONDS
        ):
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": HTTPStatus.BAD_REQUEST,
                    "error": (
                        "timeout_seconds_out_of_range"
                    ),
                    "min_timeout_seconds": 1,
                    "max_timeout_seconds": (
                        MAX_TIMEOUT_SECONDS
                    ),
                },
            )
            return

        self._execute(
            command,
            timeout_seconds,
        )

    def _authenticate(self) -> bool:
        authorization = self.headers.get(
            "Authorization",
            "",
        )

        if not authorization.startswith(
            "Bearer "
        ):
            json_response(
                self,
                HTTPStatus.UNAUTHORIZED,
                {
                    "ok": False,
                    "error": (
                        "missing_bearer_token"
                    ),
                },
            )
            return False

        supplied_token = (
            authorization.removeprefix(
                "Bearer "
            ).strip()
        )

        if not hmac.compare_digest(
            supplied_token,
            TOKEN,
        ):
            json_response(
                self,
                HTTPStatus.UNAUTHORIZED,
                {
                    "ok": False,
                    "error": "invalid_token",
                },
            )
            return False

        return True

    def _execute(
        self,
        command: str,
        timeout_seconds: int,
    ) -> None:
        digest = command_hash(
            command
        )

        LOGGER.info(
            "terminal_command_start",
            extra={
                "command_sha256": digest,
                "timeout_seconds": (
                    timeout_seconds
                ),
            },
        )

        process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            cwd="/workspace",
            start_new_session=True,
        )

        timed_out = False

        try:
            (
                stdout_data,
                stderr_data,
            ) = process.communicate(
                timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True

            process.kill()

            (
                stdout_data,
                stderr_data,
            ) = process.communicate()

            if exc.stdout:
                stdout_data = (
                    exc.stdout
                    + stdout_data
                )

            if exc.stderr:
                stderr_data = (
                    exc.stderr
                    + stderr_data
                )

        (
            stdout,
            stdout_truncated,
        ) = truncate_output(
            stdout_data
        )

        (
            stderr,
            stderr_truncated,
        ) = truncate_output(
            stderr_data
        )

        return_code = (
            process.returncode
        )

        LOGGER.info(
            "terminal_command_complete",
            extra={
                "command_sha256": digest,
                "return_code": return_code,
                "timed_out": timed_out,
                "stdout_truncated": (
                    stdout_truncated
                ),
                "stderr_truncated": (
                    stderr_truncated
                ),
            },
        )

        json_response(
            self,
            HTTPStatus.OK,
            {
                "ok": (
                    not timed_out
                    and return_code == 0
                ),
                "timed_out": timed_out,
                "return_code": return_code,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": (
                    stdout_truncated
                ),
                "stderr_truncated": (
                    stderr_truncated
                ),
                "command_sha256": digest,
                "timeout_seconds": (
                    timeout_seconds
                ),
            },
        )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get(
            "LOG_LEVEL",
            "INFO",
        ).upper(),
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
    )

    server = ThreadingHTTPServer(
        (
            HOST,
            PORT,
        ),
        TerminalExecutorHandler,
    )

    LOGGER.info(
        "terminal_executor_started",
        extra={
            "host": HOST,
            "port": PORT,
            "token_file": str(
                TOKEN_FILE
            ),
        },
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info(
            "terminal_executor_stopping"
        )
    finally:
        server.server_close()


if __name__ == "__main__":
    main()