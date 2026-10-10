from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from local_mcp_server.mcp.decorators import domain_tool
from local_mcp_server.mcp.exceptions import (
    LocalMCPError,
    SandboxNotReadyError,
    TargetContentNotFoundError,
)


def test_domain_tool_translates_local_mcp_error():
    @domain_tool
    def failing_tool():
        raise SandboxNotReadyError("my-box", hint="Please start it.")

    with pytest.raises(ToolError) as exc_info:
        failing_tool()

    assert "Sandbox 'my-box' is not ready. Please start it." in str(exc_info.value)


def test_domain_tool_translates_value_error():
    @domain_tool
    def failing_tool():
        raise ValueError("invalid parameter provided")

    with pytest.raises(ToolError) as exc_info:
        failing_tool()

    assert "invalid parameter provided" in str(exc_info.value)


def test_domain_tool_passes_through_existing_tool_error():
    @domain_tool
    def failing_tool():
        raise ToolError("direct tool error")

    with pytest.raises(ToolError) as exc_info:
        failing_tool()

    assert "direct tool error" in str(exc_info.value)


@pytest.mark.anyio
async def test_domain_tool_async_translates_target_not_found():
    @domain_tool
    async def failing_async_tool():
        raise TargetContentNotFoundError("target content not found in line range")

    with pytest.raises(ToolError) as exc_info:
        await failing_async_tool()

    assert "target content not found in line range" in str(exc_info.value)
