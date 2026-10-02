from __future__ import annotations

import platform
import sys
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver import Elicit, Resolve
from mcp.server.elicitation import ElicitationResult
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from .installation import (
    approve_installation,
    create_installation_request,
    execute_installation,
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
    delete_workspace_directory as delete_workspace_directory_impl,
    delete_workspace_file as delete_workspace_file_impl,
    list_workspace_grants,
    rename_workspace_path as rename_workspace_path_impl,
    write_workspace_file as write_workspace_file_impl,
)
from .workspace.sandbox_files import (
    list_sandbox_workspace_files,
    read_sandbox_workspace_text_file,
)


class SandboxDeletionApproval(BaseModel):
    approved: bool


def _sandbox_deletion_approval_message(
    *,
    sandbox_name: str,
) -> str:
    return (
        "SANDBOX DELETION APPROVAL REQUIRED\n\n"
        f"Sandbox: {sandbox_name}\n\n"
        "Deleting this sandbox permanently removes the OpenShell "
        "sandbox and its managed resources.\n\n"
        "This does not revoke the associated host workspace grant. "
        "Host workspace grants are separate authorization resources "
        "managed by the host-side workspace broker.\n\n"
        "Approve this sandbox deletion?"
    )


async def _sandbox_deletion_approval(
    *,
    name: str,
) -> Elicit[SandboxDeletionApproval]:
    return Elicit(
        _sandbox_deletion_approval_message(
            sandbox_name=name,
        ),
        SandboxDeletionApproval,
    )


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
    def list_workspace_files(
        sandbox_name: str,
    ) -> list[str]:
        """
        List regular files inside the selected OpenShell sandbox workspace.

        The sandbox name explicitly identifies the target sandbox.
        """
        return list_sandbox_workspace_files(sandbox_name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def read_workspace_text_file(
        sandbox_name: str,
        relative_path: str,
    ) -> str:
        """
        Read a UTF-8 text file from the selected OpenShell sandbox workspace.
        """
        return read_sandbox_workspace_text_file(
            sandbox_name,
            relative_path,
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
        sandbox_name: str,
        relative_path: str,
        content: str,
    ) -> str:
        """Create a new UTF-8 text file in the selected OpenShell sandbox workspace."""
        return create_workspace_file_impl(
            sandbox_name,
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
        sandbox_name: str,
        relative_path: str,
        content: str,
    ) -> str:
        """Replace the contents of an existing UTF-8 text file in the selected OpenShell sandbox workspace."""
        return write_workspace_file_impl(
            sandbox_name,
            relative_path,
            content,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def create_workspace_directory(
        sandbox_name: str,
        relative_path: str,
    ) -> str:
        """Create a directory inside the selected OpenShell sandbox workspace."""
        return create_workspace_directory_impl(
            sandbox_name,
            relative_path,
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
        sandbox_name: str,
        relative_path: str,
        new_relative_path: str,
    ) -> str:
        """Rename a file or directory inside the selected OpenShell sandbox workspace."""
        return rename_workspace_path_impl(
            sandbox_name,
            relative_path,
            new_relative_path,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def delete_workspace_file(
        sandbox_name: str,
        relative_path: str,
    ) -> str:
        """Delete a regular file inside the selected OpenShell sandbox workspace."""
        return delete_workspace_file_impl(
            sandbox_name,
            relative_path,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def delete_workspace_directory(
        sandbox_name: str,
        relative_path: str,
    ) -> str:
        """Delete a directory tree inside the selected OpenShell sandbox workspace."""
        return delete_workspace_directory_impl(
            sandbox_name,
            relative_path,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_authorized_host_workspaces() -> list[dict[str, object]]:
        """
        List human-authorized host workspace grants.

        These are host-directory capabilities and are distinct from
        OpenShell logical workspaces.
        """
        return list_workspace_grants()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def create_sandbox(
        name: str,
        host_workspace_id: str,
    ) -> str:
        """
        Create an OpenShell sandbox using an authorized host workspace grant.

        host_workspace_id is an opaque host-directory authorization
        capability. It is not an OpenShell workspace name.
        """
        return create_sandbox_impl(
            name=name,
            workspace_id=host_workspace_id,
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
        """List OpenShell sandboxes in the configured OpenShell workspace."""
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
        return sandbox_status_impl(name)

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
        """Execute a normal command inside an OpenShell sandbox."""
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
        request = create_installation_request(
            sandbox_name=sandbox_name,
            tool_name=tool_name,
            version=version,
            source=source,
            install_command=install_command,
            reason=reason,
        )

        approved = approve_installation(
            request.request_id,
        )

        return execute_installation(
            approved,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def delete_sandbox(
        name: str,
        approval: Annotated[
            ElicitationResult[SandboxDeletionApproval],
            Resolve(_sandbox_deletion_approval),
        ],
    ) -> str:
        """
        Delete an OpenShell sandbox after explicit user approval.

        The approval is implemented through MCP resolver-based elicitation,
        so it works with both legacy elicitation and modern MCP
        multi-round-trip clients.

        Deleting a sandbox does not revoke its associated host workspace
        grant. Host workspace grants are separate authorization resources.
        """
        if approval.action != "accept" or approval.data is None:
            return "Sandbox deletion was denied or cancelled by the user."

        if not approval.data.approved:
            return "Sandbox deletion was denied or cancelled by the user."

        return delete_sandbox_impl(name)
