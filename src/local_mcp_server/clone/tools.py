from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .service import clone_page as clone_page_impl
from .service import clone_preview as clone_preview_impl
from .service import clone_region as clone_region_impl


def register_tools(mcp: MCPServer) -> None:
    """Register static clone generation tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def clone_preview(
        sandbox_name: str,
        page_id: int,
        selector: str | None = None,
    ) -> dict[str, object]:
        """Preview a page or selected DOM region before writing any clone files."""
        return clone_preview_impl(
            sandbox_name=sandbox_name,
            page_id=page_id,
            selector=selector,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def clone_region(
        sandbox_name: str,
        page_id: int,
        selector: str,
        output_dir: str = "clones",
    ) -> dict[str, object]:
        """Create a sanitized static clone of one DOM region in the sandbox workspace."""
        return clone_region_impl(
            sandbox_name=sandbox_name,
            page_id=page_id,
            selector=selector,
            output_dir=output_dir,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def clone_page(
        sandbox_name: str,
        page_id: int,
        output_dir: str = "clones",
    ) -> dict[str, object]:
        """Create a sanitized static clone of the current browser page."""
        return clone_page_impl(
            sandbox_name=sandbox_name,
            page_id=page_id,
            output_dir=output_dir,
        )
