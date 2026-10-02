from __future__ import annotations

import platform
import sys
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver import Elicit, Resolve
from mcp.server.elicitation import ElicitationResult
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from .service import (
    create_sandbox as create_sandbox_impl,
    delete_sandbox as delete_sandbox_impl,
    execute_sandbox as execute_sandbox_impl,
    list_sandboxes as list_sandboxes_impl,
    sandbox_status as sandbox_status_impl,
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


def register_tools(mcp: MCPServer) -> None:
    """Register this domain MCP tools."""

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
