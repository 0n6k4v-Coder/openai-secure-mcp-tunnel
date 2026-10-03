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
    recreate_sandbox as recreate_sandbox_impl,
    repair_sandbox as repair_sandbox_impl,
    restart_sandbox as restart_sandbox_impl,
    sandbox_logs as sandbox_logs_impl,
    sandbox_status as sandbox_status_impl,
    start_sandbox as start_sandbox_impl,
    stop_sandbox as stop_sandbox_impl,
)
from .policy import validate_profile


class SandboxDeletionApproval(BaseModel):
    approved: bool


class SandboxRecreationApproval(BaseModel):
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


def _sandbox_recreation_approval_message(
    *,
    sandbox_name: str,
) -> str:
    return (
        "SANDBOX RECREATION APPROVAL REQUIRED\n\n"
        f"Sandbox: {sandbox_name}\n\n"
        "Recreating this sandbox permanently deletes the current "
        "OpenShell sandbox before creating a new sandbox with the "
        "same managed host workspace and profile.\n\n"
        "The current sandbox runtime state and sandbox-specific state "
        "will not be preserved. Static sandbox controls and other "
        "instance-specific state may be reset.\n\n"
        "Approve this sandbox recreation?"
    )


async def _sandbox_recreation_approval(
    *,
    name: str,
) -> Elicit[SandboxRecreationApproval]:
    return Elicit(
        _sandbox_recreation_approval_message(
            sandbox_name=name,
        ),
        SandboxRecreationApproval,
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
        profile: str = "default",
    ) -> str:
        """
        Create an OpenShell sandbox using an authorized host workspace grant.

        profile selects the workload image and policy. Supported profiles are
        'default' and 'browser'.
        """
        profile = validate_profile(profile)

        return create_sandbox_impl(
            name=name,
            workspace_id=host_workspace_id,
            profile=profile,
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
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def sandbox_logs(
        name: str,
        since: str = "5m",
    ) -> str:
        """
        Return recent OpenShell logs for a sandbox.

        since is an OpenShell duration such as '5m', '1h', or '30s'.
        """
        return sandbox_logs_impl(
            name=name,
            since=since,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def start_sandbox(
        name: str,
    ) -> str:
        """
        Start a stopped or retained failed OpenShell sandbox.
        """
        return start_sandbox_impl(name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def stop_sandbox(
        name: str,
    ) -> str:
        """Stop an OpenShell sandbox while retaining its state."""
        return stop_sandbox_impl(name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def restart_sandbox(
        name: str,
    ) -> str:
        """
        Restart an OpenShell sandbox by stopping it and starting it again.
        """
        return restart_sandbox_impl(name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def repair_sandbox(
        name: str,
    ) -> str:
        """
        Retry startup of a retained failed OpenShell sandbox.

        Repair does not delete or recreate the sandbox.
        """
        return repair_sandbox_impl(name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def recreate_sandbox(
        name: str,
        approval: Annotated[
            ElicitationResult[SandboxRecreationApproval],
            Resolve(_sandbox_recreation_approval),
        ],
    ) -> str:
        """
        Delete and recreate a managed sandbox after explicit user approval.

        The recreated sandbox keeps the managed host workspace grant and
        sandbox profile recorded by this application.
        """
        if approval.action != "accept" or approval.data is None:
            return "Sandbox recreation was denied or cancelled by the user."

        if not approval.data.approved:
            return "Sandbox recreation was denied or cancelled by the user."

        return recreate_sandbox_impl(name)

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
        """
        if approval.action != "accept" or approval.data is None:
            return "Sandbox deletion was denied or cancelled by the user."

        if not approval.data.approved:
            return "Sandbox deletion was denied or cancelled by the user."

        return delete_sandbox_impl(name)

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