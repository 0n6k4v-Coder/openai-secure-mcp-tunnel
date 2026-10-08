from __future__ import annotations

import os
from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp
from mcp.types import ToolAnnotations

from ...terminal.service import open_terminal

TERMINAL_APP_URI = "ui://terminal/view"
DEFAULT_TERMINAL_APP_DOMAIN = "https://terminal.openai-secure-mcp-tunnel.internal"

TERMINAL_BUNDLE = Path(__file__).with_name("terminal.js").read_text(encoding="utf-8")
TERMINAL_CSS = Path(__file__).with_name("terminal.css").read_text(encoding="utf-8")

TERMINAL_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sandbox Live Terminal</title>
  <style>{TERMINAL_CSS}</style>
  <style>
    :root {
      color-scheme: dark;
    }

    html,
    body {
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      overflow: hidden;
      background: #0b0f14;
    }

    body {
      display: flex;
      flex-direction: column;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
        "Liberation Mono", "Courier New", monospace;
    }

    #header {
      height: 34px;
      min-height: 34px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 10px;
      box-sizing: border-box;
      border-bottom: 1px solid #26303a;
      background: #111820;
      color: #d7dee7;
      font-size: 12px;
    }

    #title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
    }

    #status {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      color: #8f9ba8;
      font-weight: 400;
    }

    #status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #777;
    }

    #status.connected #status-dot {
      background: #43d17a;
    }

    #status.error #status-dot {
      background: #ef6461;
    }

    #terminal-container {
      flex: 1;
      min-height: 0;
      padding: 8px;
      box-sizing: border-box;
      background: #000;
    }

    #terminal {
      width: 100%;
      height: 100%;
    }
  </style>
</head>

<body>
  <div id="header">
    <div id="title">
      <span>Sandbox Terminal</span>
      <span id="status">
        <span id="status-dot"></span>
        <span id="status-text">Connecting</span>
      </span>
    </div>
    <span id="terminal-meta">OpenShell PTY</span>
  </div>

  <div id="terminal-container">
    <div id="terminal"></div>
  </div>

  <script type="module">
    {TERMINAL_BUNDLE}
  </script>
</body>
</html>
"""

TERMINAL_HTML = TERMINAL_HTML.replace("{TERMINAL_BUNDLE}", TERMINAL_BUNDLE).replace("{TERMINAL_CSS}", TERMINAL_CSS)


def register_terminal_app(apps: Apps) -> None:
    """Register the terminal MCP App resource and its UI-bound tool."""

    @apps.tool(
        resource_uri=TERMINAL_APP_URI,
        title="Open Sandbox Terminal",
        description=(
            "Open a persistent interactive PTY terminal in an OpenShell sandbox "
            "and display it as a live terminal UI when MCP Apps are supported."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    def terminal_open(
        sandbox: str,
        command: list[str] | None = None,
        cols: int = 80,
        rows: int = 24,
    ) -> dict[str, object]:
        """
        Open a persistent interactive PTY terminal session.

        The returned terminal metadata is available to the MCP App as
        structured tool output. Non-MCP-App clients receive the same data
        through the normal MCP tool result.
        """
        return open_terminal(
            sandbox=sandbox,
            command=command,
            cols=cols,
            rows=rows,
        )

    terminal_domain = (
        os.environ.get("MCP_TERMINAL_APP_DOMAIN", "").strip()
        or DEFAULT_TERMINAL_APP_DOMAIN
    )

    apps.add_html_resource(
        TERMINAL_APP_URI,
        TERMINAL_HTML,
        title="Sandbox Live Terminal",
        description="Interactive terminal connected to an OpenShell sandbox PTY.",
        domain=terminal_domain,
        csp=ResourceCsp(),
        prefers_border=True,
    )
