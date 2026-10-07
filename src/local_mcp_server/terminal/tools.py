from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .service import (
    close_terminal,
    get_terminal_state,
    list_terminals,
    open_terminal,
    resize_terminal,
    write_terminal,
)


def register_tools(mcp: MCPServer) -> None:
    """Register MCP tools for interactive terminal capability."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def terminal_open(
        sandbox: str,
        command: list[str] | None = None,
        cols: int = 80,
        rows: int = 24,
    ) -> dict[str, Any]:
        """
        Open a persistent interactive PTY terminal session to an OpenShell sandbox.

        Args:
            sandbox: Name of the target OpenShell sandbox.
            command: Optional command list to launch (defaults to interactive login shell).
            cols: Initial terminal column width (defaults to 80).
            rows: Initial terminal row height (defaults to 24).
        """
        return open_terminal(sandbox=sandbox, command=command, cols=cols, rows=rows)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def terminal_input(
        terminal_id: str,
        data: str,
    ) -> dict[str, Any]:
        """
        Send raw keyboard / stdin data to an active interactive terminal session.

        Args:
            terminal_id: Identifier of the active terminal session.
            data: Raw characters, escape codes, or text to write to terminal stdin.
        """
        return write_terminal(terminal_id=terminal_id, data=data)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def terminal_resize(
        terminal_id: str,
        cols: int,
        rows: int,
    ) -> dict[str, Any]:
        """
        Resize the virtual PTY window dimensions for an active terminal session.

        Args:
            terminal_id: Identifier of the active terminal session.
            cols: New terminal column width.
            rows: New terminal row height.
        """
        return resize_terminal(terminal_id=terminal_id, cols=cols, rows=rows)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def terminal_state(
        terminal_id: str,
        clear_buffer: bool = True,
    ) -> dict[str, Any]:
        """
        Read the latest buffered terminal stdout/stderr output and current session status.

        Args:
            terminal_id: Identifier of the active terminal session.
            clear_buffer: Whether to clear read bytes from the buffer (defaults to True).
        """
        return get_terminal_state(terminal_id=terminal_id, clear_buffer=clear_buffer)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def terminal_close(
        terminal_id: str,
    ) -> dict[str, Any]:
        """
        Terminate and cleanly close an active terminal session.

        Args:
            terminal_id: Identifier of the active terminal session.
        """
        return close_terminal(terminal_id=terminal_id)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def terminal_list(
        sandbox: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all currently active or recent terminal sessions.

        Args:
            sandbox: Optional sandbox name filter.
        """
        return list_terminals(sandbox=sandbox)
