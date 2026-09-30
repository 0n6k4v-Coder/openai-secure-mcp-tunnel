from __future__ import annotations

import platform
import sys

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

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
    list_workspace_files as list_workspace_files_impl,
    read_workspace_text_file as read_workspace_text_file_impl,
    rename_workspace_path as rename_workspace_path_impl,
    write_workspace_file as write_workspace_file_impl,
)


def register_tools(mcp: MCPServer) -> None:
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
        """List regular files below the workspace."""
        return list_workspace_files_impl()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def read_workspace_text_file(relative_path: str) -> str:
        """Read a UTF-8 text file from the workspace."""
        return read_workspace_text_file_impl(relative_path)

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
        """Create a new UTF-8 text file in the workspace."""
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
    def create_workspace_directory(relative_path: str) -> str:
        """Create a directory inside the workspace."""
        return create_workspace_directory_impl(relative_path)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def rename_workspace_path(
        relative_path: str,
        new_relative_path: str,
    ) -> str:
        """Rename a file or directory inside the workspace."""
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
    def delete_workspace_file(relative_path: str) -> str:
        """Delete a regular file inside the workspace."""
        return delete_workspace_file_impl(relative_path)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def delete_workspace_directory(relative_path: str) -> str:
        """Delete a directory tree inside the workspace."""
        return delete_workspace_directory_impl(relative_path)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def create_sandbox(name: str) -> str:
        """Create and wait for an OpenShell sandbox."""
        return create_sandbox_impl(name)

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
    def sandbox_status(name: str) -> str:
        """Return the status of an OpenShell sandbox."""
        return sandbox_status_impl(name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def execute_sandbox_command(
        name: str,
        command: str,
    ) -> str:
        """Execute a command inside an OpenShell sandbox."""
        return execute_sandbox_impl(
            sandbox_name=name,
            command=command,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def delete_sandbox(name: str) -> str:
        """Delete an OpenShell sandbox and its managed resources."""
        return delete_sandbox_impl(name)
