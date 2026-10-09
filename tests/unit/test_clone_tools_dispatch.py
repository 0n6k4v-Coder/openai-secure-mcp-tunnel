from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from mcp.server import MCPServer
from local_mcp_server.clone.tools import register_tools


@pytest.mark.anyio
async def test_clone_tools_do_not_recurse() -> None:
    mcp = MCPServer("test")
    register_tools(mcp)
    ctx = MagicMock()

    # Pure functions
    tools_to_test = [
        ("analyze_structure", {"evidence": {"discover": {"pages": []}}}),
        ("build_dependency_graph", {"evidence": {}}),
        ("create_clone_manifest", {"evidence": {"discover": {"url": "https://example.com"}}}),
        ("verify_clone", {"evidence": {}}),
        ("repair_clone", {"evidence": {}}),
        ("run_clone_workflow", {"workflow": "quick", "inputs": {"sandbox_name": "test-sbx", "url": "https://example.com"}}),
    ]

    for tool_name, args in tools_to_test:
        tool = mcp._tool_manager.get_tool(tool_name)
        assert tool is not None, f"Tool {tool_name} not registered"
        result = await tool.run(arguments=args, context=ctx)
        assert result is not None
