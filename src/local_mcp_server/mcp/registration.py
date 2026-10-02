from __future__ import annotations

from mcp.server import MCPServer

from .tools import register_tools


def register_all_tools(mcp: MCPServer) -> None:
    """Register the complete MCP tool surface."""
    register_tools(mcp)
