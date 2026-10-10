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
    run_command as run_command_impl,
    sandbox_logs as sandbox_logs_impl,
    sandbox_status as sandbox_status_impl,
    start_sandbox as start_sandbox_impl,
    stop_sandbox as stop_sandbox_impl,
    update_sandbox_description as update_sandbox_description_impl,
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
        description: str | None = None,
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
        :param description: Optional description of the sandbox's purpose or workload
            (max 250 characters).
        """
        profile = validate_profile(profile)

        return create_sandbox_impl(
            name=name,
            workspace_id=host_workspace_id,
            profile=profile,
            description=description,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def update_sandbox_description(
        name: str,
        description: str | None = None,
    ) -> str:
        """
        Update the description of an existing OpenShell sandbox.

        :param name: Unique identifier of the sandbox.
        :param description: Optional description of the sandbox's purpose or workload
            (max 250 characters). Pass null or empty string to clear.
        """
        return update_sandbox_description_impl(
            name=name,
            description=description,
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
    def run_command(
        sandbox_name: str,
        command: str,
        cwd: str | None = None,
        timeout_seconds: int = 120,
    ) -> str:
        """
        Execute a shell command inside an OpenShell sandbox workspace.

        :param sandbox_name: Unique identifier of the sandbox.
        :param command: Shell command to execute.
        :param cwd: Optional working directory relative to /workspace/project (defaults to workspace root).
        :param timeout_seconds: Maximum execution time in seconds (default: 120).
        """
        return run_command_impl(
            sandbox_name=sandbox_name,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
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

