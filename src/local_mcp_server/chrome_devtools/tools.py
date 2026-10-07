from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .service import execute_chrome_devtools


def register_tools(mcp: MCPServer) -> None:
    """Register Chrome DevTools domain MCP tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def execute_chrome_devtools_command(
        sandbox_name: str,
        command: str,
        arguments: list[str] | None = None,
    ) -> dict[str, object]:
        """
        Execute a Chrome DevTools CLI command in an existing browser sandbox.

        IMPORTANT: This operation REQUIRES a sandbox created with profile='browser'.
        It will fail if invoked on a 'default' profile sandbox (such as general development sandboxes).
        To use this tool, first create or target a browser sandbox (e.g. `create_sandbox(name=..., profile='browser')`).

        :param sandbox_name: Name of an existing sandbox running with profile='browser'.
        :param command: Chrome DevTools CLI command (e.g. 'list_pages', 'new_page', 'eval').
        :param arguments: Optional command-line arguments passed to the DevTools command.
        """
        return execute_chrome_devtools(
            sandbox_name=sandbox_name,
            command=command,
            arguments=arguments,
        )
