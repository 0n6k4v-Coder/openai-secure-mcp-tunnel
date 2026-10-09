from __future__ import annotations

from mcp.server.apps import Apps

from .terminal import register_terminal_app


def register_all_apps(apps: Apps) -> None:
    """Register all MCP Apps resources."""
    register_terminal_app(apps)
