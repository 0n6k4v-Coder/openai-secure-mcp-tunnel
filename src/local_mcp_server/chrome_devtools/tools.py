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

        The browser is the Chrome instance managed by the selected browser
        sandbox. The caller cannot select or override the Chrome connection
        endpoint.
        """
        return execute_chrome_devtools(
            sandbox_name=sandbox_name,
            command=command,
            arguments=arguments,
        )
