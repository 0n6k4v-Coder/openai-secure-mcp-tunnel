import hashlib
import json
import logging
import os
import platform
import socket
import uuid
from collections.abc import Mapping

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .tools import register_tools


SERVICE_NAME = "local-computer"
SERVICE_VERSION = "0.1.0"

INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"

logger = logging.getLogger(__name__)

mcp = MCPServer(
    SERVICE_NAME,
    version=SERVICE_VERSION,
)


async def _tool_registry_snapshot() -> tuple[list[str], str]:
    """
    Return the currently registered MCP tool names and a stable fingerprint.

    This is intentionally queried at request time so that we can detect
    whether the tool registry changes between requests.
    """
    tools = await mcp.list_tools()

    names = sorted(tool.name for tool in tools)

    fingerprint = hashlib.sha256(
        json.dumps(
            names,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:16]

    return names, fingerprint


def _get_request_value(ctx, name: str, default=None):
    """
    Safely read an attribute from ServerRequestContext.

    Different MCP SDK versions expose slightly different context fields,
    so diagnostics must never cause the actual MCP request to fail.
    """
    try:
        return getattr(ctx, name, default)
    except Exception:
        return default


def _extract_tool_name(ctx) -> str | None:
    """
    Extract the requested MCP tool name from request params when available.
    """
    params = _get_request_value(ctx, "params")

    if isinstance(params, Mapping):
        name = params.get("name")

        if isinstance(name, str):
            return name

    return None


async def request_logging_middleware(ctx, call_next):
    """
    Log every MCP request and the state of the tool registry at that moment.

    This middleware covers all current and future MCP tools without requiring
    logging code inside each individual tool.
    """
    request_id = _get_request_value(ctx, "request_id")
    method = _get_request_value(ctx, "method")
    protocol_version = _get_request_value(ctx, "protocol_version")
    session_id = _get_request_value(ctx, "session_id")

    tool_name = _extract_tool_name(ctx)

    try:
        tool_names, registry_fingerprint = await _tool_registry_snapshot()
    except Exception:
        tool_names = []
        registry_fingerprint = "registry-read-error"

        logger.exception(
            "MCP registry inspection failed "
            "instance_id=%s pid=%s method=%s request_id=%s",
            INSTANCE_ID,
            os.getpid(),
            method,
            request_id,
        )

    tool_registered = tool_name in tool_names if tool_name is not None else None

    logger.info(
        "MCP REQUEST "
        "instance_id=%s "
        "pid=%s "
        "method=%s "
        "request_id=%s "
        "protocol_version=%s "
        "session_id=%s "
        "tool=%s "
        "tool_registered=%s "
        "registry_count=%d "
        "registry_fingerprint=%s "
        "registry_tools=%s",
        INSTANCE_ID,
        os.getpid(),
        method,
        request_id,
        protocol_version,
        session_id,
        tool_name,
        tool_registered,
        len(tool_names),
        registry_fingerprint,
        json.dumps(tool_names, separators=(",", ":")),
    )

    try:
        result = await call_next(ctx)

        logger.info(
            "MCP RESPONSE "
            "instance_id=%s "
            "pid=%s "
            "method=%s "
            "request_id=%s "
            "tool=%s "
            "status=success",
            INSTANCE_ID,
            os.getpid(),
            method,
            request_id,
            tool_name,
        )

        return result

    except Exception as exc:
        logger.exception(
            "MCP RESPONSE "
            "instance_id=%s "
            "pid=%s "
            "method=%s "
            "request_id=%s "
            "tool=%s "
            "status=error "
            "error_type=%s "
            "error=%s",
            INSTANCE_ID,
            os.getpid(),
            method,
            request_id,
            tool_name,
            type(exc).__name__,
            str(exc),
        )

        raise


# Register the middleware once.
#
# Because this middleware runs at the MCP request layer, every MCP request
# is logged, including:
#
#   get_system_info
#   list_workspace_files
#   read_workspace_text_file
#   create_workspace_file
#   write_workspace_file
#   create_workspace_directory
#   rename_workspace_path
#   delete_workspace_file
#   delete_workspace_directory
#   create_sandbox
#   list_sandboxes
#   sandbox_status
#   execute_sandbox_command
#   delete_sandbox
mcp.middleware.append(request_logging_middleware)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):
    """
    Simple HTTP health endpoint.
    """
    from starlette.responses import JSONResponse

    return JSONResponse(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "instance_id": INSTANCE_ID,
            "pid": os.getpid(),
        }
    )


# Register all application tools.
register_tools(mcp)


def main() -> None:
    """
    Start the local MCP server.
    """
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format=("%(asctime)s %(levelname)s %(name)s %(message)s"),
    )

    logger.info(
        "Starting MCP server "
        "service=%s "
        "version=%s "
        "instance_id=%s "
        "pid=%s "
        "hostname=%s "
        "python=%s",
        SERVICE_NAME,
        SERVICE_VERSION,
        INSTANCE_ID,
        os.getpid(),
        socket.gethostname(),
        platform.python_version(),
    )

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "mcp-server:8000",
        ],
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
