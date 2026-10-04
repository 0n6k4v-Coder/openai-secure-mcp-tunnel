from __future__ import annotations

from mcp.server import MCPServer

from ..chrome_devtools.tools import register_tools as register_chrome_devtools_tools
from ..installation.tools import register_tools as register_installation_tools
from ..sandbox.tools import register_tools as register_sandbox_tools
from ..workspace.tools import register_tools as register_workspace_tools


def register_all_tools(mcp: MCPServer) -> None:
    """Register the complete MCP tool surface."""
    register_workspace_tools(mcp)
    register_sandbox_tools(mcp)
    register_installation_tools(mcp)
    register_chrome_devtools_tools(mcp)
