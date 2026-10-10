from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .service import (
    create_directory as create_directory_impl,
    delete_directory as delete_directory_impl,
    delete_file as delete_file_impl,
    list_files as list_files_impl,
    list_workspace_grants,
    rename_path as rename_path_impl,
    replace_file_content as replace_file_content_impl,
    view_file as view_file_impl,
    write_to_file as write_to_file_impl,
)


def register_tools(mcp: MCPServer) -> None:
    """Register file and directory management MCP tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def list_files(
        sandbox_name: str,
        path: str | None = None,
        directory: str | None = None,
    ) -> list[str]:
        """
        List regular files inside the selected OpenShell sandbox workspace.

        The sandbox name explicitly identifies the target sandbox.
        Optionally filter results by a relative directory path (e.g. 'apps/wise/live-proxy').
        """
        all_files = list_files_impl(sandbox_name)
        filter_path = path or directory
        if filter_path:
            clean = filter_path.strip().strip("/")
            return [f for f in all_files if f == clean or f.startswith(f"{clean}/")]
        return all_files

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def view_file(
        sandbox_name: str,
        relative_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        content_offset: int | None = None,
        path: str | None = None,
    ) -> str:
        """
        View the contents of a file in the selected OpenShell sandbox workspace.
        This tool supports text files and binary files.

        Text file usage:
        - The lines of the file are 1-indexed
        - You can view at most 800 lines at a time
        - Specify start_line and end_line to view the lines of the file using slice notation:
          - Omit both to view the entire file, or the first 800 lines of the file, whichever is smaller.
          - Specify start_line only to view the remaining lines of the file, or the next 800 lines, whichever is smaller.
          - Specify end_line only to view the remaining preceding lines of the file, or the previous 800 lines, whichever is smaller.
          - Specify both to view a precise line range. This range must be smaller than 800 lines or only the first 800 lines of the range will be shown.
        - Content is limited to 46,080 bytes per view. If content is truncated, use the content_offset parameter to view the remaining content.
        Binary file usage:
        - Do not provide start_line or end_line arguments.
        """
        target_path = relative_path or path or ""
        return view_file_impl(
            sandbox_name,
            target_path,
            start_line=start_line,
            end_line=end_line,
            content_offset=content_offset,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def write_to_file(
        sandbox_name: str,
        relative_path: str,
        content: str,
        overwrite: bool = True,
    ) -> str:
        """
        Create a new file or overwrite an existing file in the selected OpenShell sandbox.

        Supported code, markup, style, JSON/YAML, and Markdown files are formatted automatically when Prettier or Ruff
        is available in the target sandbox. The result reports whether formatting ran or
        was skipped; a missing formatter does not prevent the write.
        Parent directories are created automatically if they do not exist.
        Set overwrite=False to prevent replacing existing files.
        """
        return write_to_file_impl(
            sandbox_name=sandbox_name,
            relative_path=relative_path,
            content=content,
            overwrite=overwrite,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def replace_file_content(
        sandbox_name: str,
        relative_path: str,
        target_content: str,
        replacement_content: str,
        start_line: int | None = None,
        end_line: int | None = None,
        allow_multiple: bool = False,
    ) -> str:
        """
        Replace target content within an existing file in the selected OpenShell sandbox.

        Supported code, markup, style, JSON/YAML, and Markdown files are formatted automatically when Prettier or Ruff
        is available in the target sandbox. The result reports whether formatting ran or
        was skipped; a missing formatter does not prevent the edit.
        target_content must match existing text in the file.
        By default (allow_multiple=False), replaces exactly one unique occurrence.
        Set allow_multiple=True to replace all occurrences.

        Specify start_line and end_line (1-indexed, inclusive) to restrict the search and replacement
        to a specific range of lines.
        """
        return replace_file_content_impl(
            sandbox_name=sandbox_name,
            relative_path=relative_path,
            target_content=target_content,
            replacement_content=replacement_content,
            start_line=start_line,
            end_line=end_line,
            allow_multiple=allow_multiple,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def create_directory(
        sandbox_name: str,
        relative_path: str,
    ) -> str:
        """Create a directory inside the selected OpenShell sandbox workspace."""
        return create_directory_impl(
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
    def rename_path(
        sandbox_name: str,
        relative_path: str,
        new_relative_path: str,
    ) -> str:
        """Rename a file or directory inside the selected OpenShell sandbox workspace."""
        return rename_path_impl(
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
    def delete_file(
        sandbox_name: str,
        relative_path: str,
    ) -> str:
        """Delete a regular file inside the selected OpenShell sandbox workspace."""
        return delete_file_impl(
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
    def delete_directory(
        sandbox_name: str,
        relative_path: str,
    ) -> str:
        """Delete a directory tree inside the selected OpenShell sandbox workspace."""
        return delete_directory_impl(
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

