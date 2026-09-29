from __future__ import annotations

import logging
import os

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from .tools import register_tools

logger = logging.getLogger(__name__)

mcp = MCPServer(
    "local-computer",
    version="0.1.0",
)


@mcp.custom_route(
    "/healthz",
    methods=["GET"],
    include_in_schema=False,
)
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


register_tools(mcp)


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
