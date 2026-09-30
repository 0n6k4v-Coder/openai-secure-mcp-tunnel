from __future__ import annotations

import platform
import sys
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from .install import (
    approve_installation,
    consume_installation_approval,
    create_installation_request,
    deny_installation,
    mark_installation_finished,
)
from .sandbox import (
    create_sandbox as create_sandbox_impl,
    delete_sandbox as delete_sandbox_impl,
    execute_sandbox as execute_sandbox_impl,
    list_sandboxes as list_sandboxes_impl,
    sandbox_status as sandbox_status_impl,
)
from .workspace import (
    create_workspace_directory as create_workspace_directory_impl,
    create_workspace_file as create_workspace_file_impl,
    create_workspace_grant,
    delete_workspace_directory as delete_workspace_directory_impl,
    delete_workspace_file as delete_workspace_file_impl,
    list_workspace_files as list_workspace_files_impl,
    list_workspace_grants,
    read_workspace_text_file as read_workspace_text_file_impl,
    rename_workspace_path as rename_workspace_path_impl,
    write_workspace_file as write_workspace_file_impl,
)


class InstallationApproval(BaseModel):
    approved: bool


async def _installation_approval(
    *,
    ctx: Context,
    request_id: str,
    tool_name: str,
    version: str,
    source: str,
    install_command: str,
    reason: str,
) -> InstallationApproval:
    message = (
        "SOFTWARE INSTALLATION APPROVAL REQUIRED\n\n"
        f"Request ID: {request_id}\n"
        f"Tool: {tool_name}\n"
        f"Version: {version}\n"
        f"Source: {source}\n"
        f"Command: {install_command}\n"
        f"Reason: {reason}\n\n"
        "This approval is valid only for this exact installation request "
        "and is consumed after execution.\n\n"
        "Approve this installation?"
    )

    result = await ctx.elicit(
        message,
        InstallationApproval,
    )

    if result.action != "accept":
        deny_installation(
            request_id
        )

        return InstallationApproval(
            approved=False
        )

    if result.data is None:
        deny_installation(
            request_id
        )

        return InstallationApproval(
            approved=False
        )

    return result.data


def register_tools(
    mcp: MCPServer,
) -> None:
    """Register all MCP tools exposed by the local server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def get_system_info() -> dict[str, str]:
        """Return basic information about the local MCP container."""
        return {
            "operating_system": platform.system(),
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
        }

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_workspace_files() -> list[str]:
        """List regular files below the MCP workspace."""
        return list_workspace_files_impl()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def read_workspace_text_file(
        relative_path: str,
    ) -> str:
        """Read a UTF-8 text file from the MCP workspace."""
        return read_workspace_text_file_impl(
            relative_path
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def create_workspace_file(
        relative_path: str,
        content: str,
    ) -> str:
        """Create a new UTF-8 text file in the MCP workspace."""
        return create_workspace_file_impl(
            relative_path,
            content,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def write_workspace_file(
        relative_path: str,
        content: str,
    ) -> str:
        """Replace the contents of an existing UTF-8 text file."""
        return write_workspace_file_impl(
            relative_path,
            content,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def create_workspace_directory(
        relative_path: str,
    ) -> str:
        """Create a directory inside the MCP workspace."""
        return create_workspace_directory_impl(
            relative_path
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def rename_workspace_path(
        relative_path: str,
        new_relative_path: str,
    ) -> str:
        """Rename a file or directory inside the MCP workspace."""
        return rename_workspace_path_impl(
            relative_path,
            new_relative_path,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def delete_workspace_file(
        relative_path: str,
    ) -> str:
        """Delete a regular file inside the MCP workspace."""
        return delete_workspace_file_impl(
            relative_path
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def delete_workspace_directory(
        relative_path: str,
    ) -> str:
        """Delete a directory tree inside the MCP workspace."""
        return delete_workspace_directory_impl(
            relative_path
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def authorize_workspace(
        host_path: str,
    ) -> dict[str, str]:
        """
        Create a workspace capability for a host directory.

        The MCP client must treat this operation as a human authorization
        boundary. The returned workspace_id is the only value accepted by
        create_sandbox().
        """
        return create_workspace_grant(
            host_path
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_authorized_workspaces() -> list[dict[str, str]]:
        """List currently authorized host workspace capabilities."""
        return list_workspace_grants()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def create_sandbox(
        name: str,
        workspace_id: str,
    ) -> str:
        """
        Create a sandbox using a previously authorized workspace capability.
        """
        return create_sandbox_impl(
            name=name,
            workspace_id=workspace_id,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_sandboxes() -> str:
        """List OpenShell sandboxes."""
        return list_sandboxes_impl()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def sandbox_status(
        name: str,
    ) -> str:
        """Return the status of an OpenShell sandbox."""
        return sandbox_status_impl(
            name
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def execute_sandbox_command(
        name: str,
        command: str,
    ) -> str:
        """
        Execute a normal command inside an OpenShell sandbox.

        Software installation must use request_tool_installation().
        """
        return execute_sandbox_impl(
            name=name,
            command=command,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def request_tool_installation(
        ctx: Context,
        sandbox_name: str,
        tool_name: str,
        version: str,
        source: str,
        install_command: str,
        reason: str,
    ) -> dict[str, object]:
        """
        Request a one-time, human-approved software installation.

        The installation does not execute unless the MCP client explicitly
        accepts the elicitation request.
        """
        request = create_installation_request(
            sandbox_name=sandbox_name,
            tool_name=tool_name,
            version=version,
            source=source,
            install_command=install_command,
            reason=reason,
        )

        approval = await _installation_approval(
            ctx=ctx,
            request_id=request.request_id,
            tool_name=request.tool_name,
            version=request.version,
            source=request.source,
            install_command=request.install_command,
            reason=request.reason,
        )

        if not approval.approved:
            return {
                "request_id": request.request_id,
                "approved": False,
                "executed": False,
                "message": (
                    "Installation denied or cancelled by the user."
                ),
            }

        approved = approve_installation(
            request.request_id
        )

        consumed = consume_installation_approval(
            approved.request_id
        )

        # IMPORTANT:
        #
        # This function intentionally does not call execute_sandbox().
        #
        # A production installation worker must be the only component allowed
        # to consume InstallationRequest objects. It must:
        #
        #   1. execute consumed.install_command;
        #   2. capture stdout/stderr/exit status;
        #   3. mark_installation_finished();
        #   4. never expose a generic shell command endpoint.
        #
        # Returning the consumed request here prevents accidentally turning
        # this MCP tool into an unrestricted shell execution primitive.
        #
        # The worker should be implemented as a separately supervised service.

        mark_installation_finished(
            consumed.request_id,
            success=False,
        )

        return {
            "request_id": consumed.request_id,
            "approved": True,
            "executed": False,
            "message": (
                "Installation approval was granted and consumed, "
                "but no installation worker is configured. "
                "No command was executed."
            ),
        }

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnly=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def delete_sandbox(
        name: str,
    ) -> str:
        """Delete an OpenShell sandbox and its managed resources."""
        return delete_sandbox_impl(
            name
        )