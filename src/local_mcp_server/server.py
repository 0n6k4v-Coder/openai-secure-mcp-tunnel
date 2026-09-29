from __future__ import annotations

import logging
import os
import platform
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

mcp = MCPServer(
    "local-computer",
    version="0.1.0",
)

ALLOWED_ROOT = Path(os.environ.get("workspace_DIR", "/app/workspace")).resolve()

MAX_READ_BYTES = 1_000_000


def resolve_allowed_path(relative_path: str) -> Path:
    candidate = (ALLOWED_ROOT / relative_path).resolve()

    try:
        candidate.relative_to(ALLOWED_ROOT)
    except ValueError as exc:
        raise ValueError(
            "Requested path is outside the allowed data directory."
        ) from exc

    return candidate


@mcp.custom_route(
    "/healthz",
    methods=["GET"],
    include_in_schema=False,
)
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def get_system_info() -> dict[str, str]:
    """Return basic information about the local MCP container."""
    return {
        "operating_system": platform.system(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
    }


@mcp.tool()
def list_allowed_files() -> list[str]:
    """List files below the configured allowed data directory."""
    if not ALLOWED_ROOT.exists():
        return []

    results: list[str] = []

    for path in ALLOWED_ROOT.rglob("*"):
        try:
            resolved = path.resolve()

            if not resolved.is_file():
                continue

            resolved.relative_to(ALLOWED_ROOT)

            results.append(resolved.relative_to(ALLOWED_ROOT).as_posix())

        except OSError, ValueError:
            continue

    return sorted(results)


@mcp.tool()
def read_allowed_text_file(relative_path: str) -> str:
    """Read a UTF-8 text file under the configured allowed data directory."""
    target = resolve_allowed_path(relative_path)

    if not target.is_file():
        raise ValueError("Requested path is not a regular file.")

    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError("Requested file is too large.")

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Requested file is not valid UTF-8 text.") from exc


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    logger.info("Starting local MCP server")

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["mcp-server:8000"],
    )

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=1 * 1024 * 1024,
        transport_security=transport_security,
    )


if __name__ == "__main__":
    main()
