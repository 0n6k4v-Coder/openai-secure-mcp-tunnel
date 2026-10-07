from __future__ import annotations

import logging
import os
import platform
import socket
import uuid

from mcp.server import MCPServer
from mcp.server.apps import Apps
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from ..mcp.apps.registration import register_all_apps
from ..mcp.registration import register_all_tools
from .health import health_response
from .middleware import make_request_logging_middleware

SERVICE_NAME = "local-computer"
SERVICE_VERSION = "0.1.0"
INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"
logger = logging.getLogger(__name__)
HEALTH_ALLOWED_HOSTS = {
    "mcp-server:8000",
    "127.0.0.1:8000",
    "localhost:8000",
}

apps = Apps()
register_all_apps(apps)

mcp = MCPServer(SERVICE_NAME, version=SERVICE_VERSION, extensions=[apps])
mcp.middleware.append(make_request_logging_middleware(mcp, INSTANCE_ID))


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request):
    host = request.headers.get("host", "").strip().lower()
    if host not in HEALTH_ALLOWED_HOSTS:
        return PlainTextResponse("Invalid Host header", status_code=400)
    return health_response(
        service_name=SERVICE_NAME,
        service_version=SERVICE_VERSION,
        instance_id=INSTANCE_ID,
    )


register_all_tools(mcp)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info(
        "Starting MCP server service=%s version=%s instance_id=%s pid=%s hostname=%s python=%s",
        SERVICE_NAME,
        SERVICE_VERSION,
        INSTANCE_ID,
        os.getpid(),
        socket.gethostname(),
        platform.python_version(),
    )
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
