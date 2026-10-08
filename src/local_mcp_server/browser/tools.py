from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.types import ToolAnnotations

from .service import (
    BrowserError,
    browser_click as browser_click_impl,
    browser_drag as browser_drag_impl,
    browser_key as browser_key_impl,
    browser_move as browser_move_impl,
    browser_pointer_down as browser_pointer_down_impl,
    browser_pointer_up as browser_pointer_up_impl,
    browser_scroll as browser_scroll_impl,
    browser_type as browser_type_impl,
    evaluate as evaluate_impl,
    inspect_selector as inspect_selector_impl,
    list_pages as list_pages_impl,
    navigate_page as navigate_page_impl,
    screenshot as screenshot_impl,
    take_snapshot as take_snapshot_impl,
    viewport_frame as viewport_frame_impl,
    viewport_start as viewport_start_impl,
    viewport_stop as viewport_stop_impl,
)


def register_tools(mcp: MCPServer) -> None:
    """Register browser inspection, navigation, viewport, and input tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def browser_pages(sandbox_name: str) -> object:
        """List pages currently open in the isolated browser."""
        return list_pages_impl(sandbox_name)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_navigate(sandbox_name: str, page_id: int, url: str) -> dict[str, object]:
        """Navigate a browser page to an http(s) URL."""
        return navigate_page_impl(sandbox_name, page_id, url)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def browser_snapshot(sandbox_name: str, page_id: int, verbose: bool = False) -> dict[str, object]:
        """Capture the current page accessibility snapshot."""
        return take_snapshot_impl(sandbox_name, page_id, verbose)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def browser_screenshot(sandbox_name: str, page_id: int, full_page: bool = False) -> Image:
        """Capture the current browser page as a JPEG image."""
        return Image(data=screenshot_impl(sandbox_name, page_id, full_page=full_page), format="jpeg")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def browser_inspect(sandbox_name: str, page_id: int, selector: str) -> dict[str, object]:
        """Inspect a CSS-selected DOM element and its computed layout."""
        return inspect_selector_impl(sandbox_name, page_id, selector)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def browser_evaluate(sandbox_name: str, page_id: int, function: str) -> dict[str, object]:
        """Evaluate a bounded JavaScript function in a browser page."""
        return evaluate_impl(sandbox_name, page_id, function)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_viewport_start(sandbox_name: str, page_id: int, width: int = 1280, height: int = 800, quality: int = 70) -> dict[str, object]:
        """Start a live CDP screencast for a browser page."""
        return viewport_start_impl(sandbox_name, page_id, width=width, height=height, quality=quality)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def browser_viewport_frame(sandbox_name: str, page_id: int) -> Image | dict[str, object]:
        """Return the latest JPEG frame from the live CDP screencast."""
        data, mime = viewport_frame_impl(sandbox_name, page_id)
        if not data:
            return {"page_id": page_id, "state": "waiting"}
        return Image(data=data, format="jpeg")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def browser_viewport_stop(sandbox_name: str, page_id: int) -> dict[str, object]:
        """Stop the live CDP screencast for a browser page."""
        return viewport_stop_impl(sandbox_name, page_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_click(sandbox_name: str, page_id: int, x: float, y: float, button_name: str = "left", double: bool = False) -> dict[str, object]:
        """Click at viewport coordinates in the shared Chrome page."""
        return browser_click_impl(sandbox_name, page_id, x, y, button_name=button_name, double=double)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_move(sandbox_name: str, page_id: int, x: float, y: float, button_name: str = "none", buttons: int = 0) -> dict[str, object]:
        """Move the mouse in the shared Chrome page, optionally preserving a pressed-button state."""
        return browser_move_impl(sandbox_name, page_id, x, y, button_name=button_name, buttons=buttons)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_pointer_down(sandbox_name: str, page_id: int, x: float, y: float, button_name: str = "left") -> dict[str, object]:
        """Press and hold a mouse button in the shared Chrome page."""
        return browser_pointer_down_impl(sandbox_name, page_id, x, y, button_name=button_name)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_pointer_up(sandbox_name: str, page_id: int, x: float, y: float, button_name: str = "left") -> dict[str, object]:
        """Release a mouse button in the shared Chrome page."""
        return browser_pointer_up_impl(sandbox_name, page_id, x, y, button_name=button_name)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_scroll(sandbox_name: str, page_id: int, delta_x: float, delta_y: float, x: float = 1, y: float = 1) -> dict[str, object]:
        """Scroll the shared Chrome page using wheel input."""
        return browser_scroll_impl(sandbox_name, page_id, delta_x, delta_y, x=x, y=y)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_type(sandbox_name: str, page_id: int, text: str) -> dict[str, object]:
        """Type text into the currently focused target in the shared Chrome page."""
        return browser_type_impl(sandbox_name, page_id, text)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_key(sandbox_name: str, page_id: int, key: str) -> dict[str, object]:
        """Press a keyboard key or modifier combination in the shared Chrome page."""
        return browser_key_impl(sandbox_name, page_id, key)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def browser_drag(sandbox_name: str, page_id: int, from_x: float, from_y: float, to_x: float, to_y: float, steps: int = 8) -> dict[str, object]:
        """Drag the mouse between viewport coordinates in the shared Chrome page."""
        return browser_drag_impl(sandbox_name, page_id, from_x, from_y, to_x, to_y, steps=steps)
