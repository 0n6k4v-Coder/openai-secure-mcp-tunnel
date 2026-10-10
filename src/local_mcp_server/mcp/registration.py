from __future__ import annotations

from mcp.server import MCPServer

from .decorators import domain_tool
from ..chrome_devtools.tools import register_tools as register_chrome_devtools_tools
from ..clone.tools import register_tools as register_clone_tools
from ..sandbox.tools import register_tools as register_sandbox_tools
from ..terminal.tools import register_tools as register_terminal_tools
from ..workspace.tools import register_tools as register_workspace_tools


def register_all_tools(mcp: MCPServer) -> None:
    """Register the complete MCP tool surface with automatic domain error normalization."""
    orig_tool = mcp.tool

    def safe_tool(*args, **kwargs):
        decorator = orig_tool(*args, **kwargs)

        def wrap(fn):
            return decorator(domain_tool(fn))

        return wrap

    mcp.tool = safe_tool
    try:
        register_workspace_tools(mcp)
        register_sandbox_tools(mcp)
        register_chrome_devtools_tools(mcp)
        register_clone_tools(mcp)
        register_terminal_tools(mcp)
    finally:
        mcp.tool = orig_tool
