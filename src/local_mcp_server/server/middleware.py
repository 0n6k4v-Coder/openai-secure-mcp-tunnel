from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Mapping

from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)


def _get_request_value(ctx, name: str, default=None):
    try:
        return getattr(ctx, name, default)
    except Exception:
        return default


def _extract_tool_name(ctx) -> str | None:
    params = _get_request_value(ctx, "params")
    if isinstance(params, Mapping):
        name = params.get("name")
        if isinstance(name, str):
            return name
    return None


def make_request_logging_middleware(mcp, instance_id: str):
    async def request_logging_middleware(ctx, call_next):
        request_id = _get_request_value(ctx, "request_id")
        method = _get_request_value(ctx, "method")
        protocol_version = _get_request_value(ctx, "protocol_version")
        session_id = _get_request_value(ctx, "session_id")
        tool_name = _extract_tool_name(ctx)
        if method == "tools/call" and isinstance(ctx.params, Mapping):
            arguments = ctx.params.get("arguments", {})
            if not isinstance(arguments, Mapping):
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text="Tool arguments must be a JSON object.",
                        )
                    ],
                    isError=True,
                )
            try:
                tools_for_validation = await mcp.list_tools()
            except Exception:
                logger.exception(
                    "Unable to inspect MCP tool schemas for argument validation"
                )
                raise
            tool = next(
                (item for item in tools_for_validation if item.name == tool_name),
                None,
            )
            if tool is not None:
                schema = tool.input_schema
                properties = (
                    schema.get("properties", {}) if isinstance(schema, Mapping) else {}
                )
                if isinstance(properties, Mapping):
                    unexpected = sorted(set(arguments) - set(properties))
                    if unexpected:
                        return CallToolResult(
                            content=[
                                TextContent(
                                    type="text",
                                    text=(
                                        f"Unexpected argument(s) for tool {tool_name!r}: "
                                        + ", ".join(unexpected)
                                    ),
                                )
                            ],
                            isError=True,
                        )
        try:
            tools = await mcp.list_tools()
            tool_names = sorted(tool.name for tool in tools)
            registry_fingerprint = hashlib.sha256(
                json.dumps(tool_names, separators=(",", ":"), ensure_ascii=True).encode(
                    "utf-8"
                )
            ).hexdigest()[:16]
        except Exception:
            tool_names = []
            registry_fingerprint = "registry-read-error"
            logger.exception(
                "MCP registry inspection failed instance_id=%s pid=%s method=%s request_id=%s",
                instance_id,
                os.getpid(),
                method,
                request_id,
            )
        logger.info(
            "MCP REQUEST instance_id=%s pid=%s method=%s request_id=%s protocol_version=%s "
            "session_id=%s tool=%s tool_registered=%s registry_count=%d "
            "registry_fingerprint=%s registry_tools=%s",
            instance_id,
            os.getpid(),
            method,
            request_id,
            protocol_version,
            session_id,
            tool_name,
            tool_name in tool_names if tool_name else None,
            len(tool_names),
            registry_fingerprint,
            json.dumps(tool_names, separators=(",", ":")),
        )
        try:
            result = await call_next(ctx)
            if method == "tools/call" and isinstance(result, CallToolResult) and result.is_error:
                error_text = (
                    result.content[0].text
                    if result.content and hasattr(result.content[0], "text")
                    else "Tool execution failed"
                )
                logger.info(
                    "MCP RESPONSE instance_id=%s pid=%s method=%s request_id=%s tool=%s status=error error=%s",
                    instance_id,
                    os.getpid(),
                    method,
                    request_id,
                    tool_name,
                    error_text,
                )
            else:
                logger.info(
                    "MCP RESPONSE instance_id=%s pid=%s method=%s request_id=%s tool=%s status=success",
                    instance_id,
                    os.getpid(),
                    method,
                    request_id,
                    tool_name,
                )
            return result
        except Exception as exc:
            root_cause = getattr(exc, "__cause__", None) or exc
            error_message = str(root_cause) or str(exc)
            logger.info(
                "MCP RESPONSE instance_id=%s pid=%s method=%s request_id=%s tool=%s "
                "status=error error_type=%s error=%s",
                instance_id,
                os.getpid(),
                method,
                request_id,
                tool_name,
                type(root_cause).__name__,
                error_message,
            )
            if method == "tools/call":
                return CallToolResult(
                    content=[TextContent(type="text", text=error_message)],
                    isError=True,
                )
            raise

    return request_logging_middleware
