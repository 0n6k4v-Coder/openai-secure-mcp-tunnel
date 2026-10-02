from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .service import (
    InstallationError,
    approve_installation,
    create_installation_request,
    execute_installation,
)


def register_tools(mcp: MCPServer) -> None:
    """Register this domain MCP tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def request_tool_installation(
        sandbox_name: str,
        tool_name: str,
        version: str,
        source: str,
        install_command: str,
        reason: str,
    ) -> dict[str, object]:
        """
        Install an approved software tool inside one specific OpenShell sandbox.

        The connected MCP host must require explicit approval for this
        destructive action. The server executes only after the host has
        allowed the tool call.

        The command is validated and executed inside the requested OpenShell
        sandbox, never on the MCP server host.
        """
        try:
            request = create_installation_request(
                sandbox_name=sandbox_name,
                tool_name=tool_name,
                version=version,
                source=source,
                install_command=install_command,
                reason=reason,
            )
            approved = approve_installation(request.request_id)
            return execute_installation(approved)
        except InstallationError as exc:
            raise ToolError(str(exc)) from exc
