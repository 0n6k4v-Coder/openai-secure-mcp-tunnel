from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.types import ToolAnnotations

from .service import (
    BrowserError,
    evaluate as evaluate_impl,
    inspect_selector as inspect_selector_impl,
    list_pages as list_pages_impl,
    navigate_page as navigate_page_impl,
    screenshot as screenshot_impl,
    take_snapshot as take_snapshot_impl,
)


def register_tools(mcp: MCPServer) -> None:
    """Register isolated browser inspection and navigation tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def browser_pages(sandbox_name: str) -> object:
        """List pages currently open in the isolated browser."""
        return list_pages_impl(sandbox_name)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    def browser_navigate(
        sandbox_name: str,
        page_id: int,
        url: str,
    ) -> dict[str, object]:
        """Navigate a browser page to an http(s) URL."""
        return navigate_page_impl(sandbox_name, page_id, url)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def browser_snapshot(
        sandbox_name: str,
        page_id: int,
        verbose: bool = False,
    ) -> dict[str, object]:
        """Capture the current page accessibility snapshot."""
        return take_snapshot_impl(sandbox_name, page_id, verbose)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def browser_screenshot(
        sandbox_name: str,
        page_id: int,
        full_page: bool = False,
    ) -> Image:
        """Capture the current browser page as a PNG image."""
        return Image(
            data=screenshot_impl(
                sandbox_name,
                page_id,
                full_page=full_page,
            ),
            format="png",
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def browser_inspect(
        sandbox_name: str,
        page_id: int,
        selector: str,
    ) -> dict[str, object]:
        """Inspect a CSS-selected DOM element and its computed layout."""
        return inspect_selector_impl(sandbox_name, page_id, selector)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def browser_evaluate(
        sandbox_name: str,
        page_id: int,
        function: str,
    ) -> dict[str, object]:
        """Evaluate a bounded JavaScript function in a browser page."""
        return evaluate_impl(sandbox_name, page_id, function)
