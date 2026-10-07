from __future__ import annotations

import platform
import sys
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .policy import validate_profile
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
        host_workspace_id: str | None = None,
        profile: str = "default",
    ) -> str:
        """
        Create an OpenShell sandbox.

        :param name: Unique identifier for the sandbox. Must be 1 to 19 characters,
            start with a letter or digit, and contain only lowercase letters, digits,
            and hyphens (matching regex `^[a-z0-9][a-z0-9-]{0,18}$`). Underscores,
            uppercase letters, and names exceeding 19 characters are rejected.
        :param host_workspace_id: Optional authorized host workspace ID.
            When supplied, mounts the host workspace directory into `/workspace/project`.
            When omitted, creates a standalone sandbox using its own local filesystem.
        :param profile: Selects the workload image and runtime policy.
            - 'default': General development environment (Python/Node/Linux utilities).
            - 'browser': Includes headless Chrome and DevTools daemon (required for
              `execute_chrome_devtools_command`).
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
        """Start a stopped or retained failed OpenShell sandbox."""
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
        """Restart an OpenShell sandbox by stopping and starting it."""
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
        """Retry startup of a retained failed OpenShell sandbox."""
        return repair_sandbox_impl(name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def recreate_sandbox(
        name: str,
    ) -> str:
        """Delete and recreate a sandbox preserving profile and workspace binding."""
        return recreate_sandbox_impl(name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def delete_sandbox(
        name: str,
    ) -> str:
        """Permanently delete an OpenShell sandbox."""
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def get_sandbox_capabilities(name: str) -> dict[str, Any]:
        """
        Inspect capabilities granted to an OpenShell sandbox (e.g. docker, openshell).

        Args:
            name: The target sandbox name.
        """
        from ..capability.service import inspect_sandbox_capabilities
        return inspect_sandbox_capabilities(name)

