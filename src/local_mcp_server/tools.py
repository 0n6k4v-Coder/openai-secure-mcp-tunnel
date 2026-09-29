from __future__ import annotations

import platform
import sys

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .terminal import (
    execute_terminal_command_impl,
)
from .workspace import (
    create_workspace_directory as create_workspace_directory_impl,
    create_workspace_file as create_workspace_file_impl,
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
            idempotentHint=True,
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
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def execute_terminal_command(
        command: str,
        timeout_seconds: int = 30,
    ) -> str:
        """
        Execute an arbitrary command on the host operating system.

        This is a high-impact tool. The MCP client must be configured to
        require user approval before each invocation.
        """
        return execute_terminal_command_impl(
            command=command,
            timeout_seconds=timeout_seconds,
        )
