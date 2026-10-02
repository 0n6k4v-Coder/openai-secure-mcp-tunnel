from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .service import (
    create_workspace_directory as create_workspace_directory_impl,
    create_workspace_file as create_workspace_file_impl,
    delete_workspace_directory as delete_workspace_directory_impl,
    delete_workspace_file as delete_workspace_file_impl,
    list_sandbox_workspace_files,
    list_workspace_grants,
    read_sandbox_workspace_text_file,
    rename_workspace_path as rename_workspace_path_impl,
    write_workspace_file as write_workspace_file_impl,
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
