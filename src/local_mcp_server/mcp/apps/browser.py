from __future__ import annotations

import os
from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp
from mcp.types import ToolAnnotations

from ...browser.service import open_page

BROWSER_APP_URI = "ui://browser/view"
DEFAULT_BROWSER_APP_DOMAIN = "https://browser.openai-secure-mcp-tunnel.internal"

BROWSER_BUNDLE = Path(__file__).with_name("browser.js").read_text(encoding="utf-8")

BROWSER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sandbox Browser</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    html, body { width:100%; height:100%; margin:0; background:#0b0f14; color:#d7dee7; font:13px ui-sans-serif,system-ui,sans-serif; }
    body { display:flex; flex-direction:column; }
    header { height:38px; min-height:38px; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border-bottom:1px solid #26303a; background:#111820; }
    #status { color:#8f9ba8; }
    #status[data-kind="ok"] { color:#43d17a; }
    #status[data-kind="error"] { color:#ef6461; }
    main { flex:1; min-height:0; overflow:auto; padding:10px; }
    .controls,.actions { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
    input,button { border:1px solid #34404d; background:#151d26; color:#e6edf3; border-radius:6px; padding:7px 9px; }
    input:focus { outline:1px solid #6ea8fe; }
    #url { flex:1; min-width:260px; }
    #selector { flex:1; min-width:220px; }
    button { cursor:pointer; }
    button:hover { background:#1b2632; }
    #screenshot { width:100%; max-height:55vh; object-fit:contain; background:#000; border:1px solid #26303a; border-radius:6px; margin:8px 0; }
    #output { white-space:pre-wrap; word-break:break-word; margin:0; padding:10px; background:#080b0f; border:1px solid #26303a; border-radius:6px; max-height:38vh; overflow:auto; }
  </style>
</head>
<body>
  <header>
    <strong>Sandbox Browser</strong>
    <span id="status">Connecting…</span>
  </header>
  <main>
    <section class="controls">
      <input id="url" type="url" placeholder="https://example.com">
      <button id="open">Open</button>
      <label>Page <input id="page" type="number" min="0" value="1" style="width:72px"></label>
      <input id="selector" placeholder="CSS selector, e.g. main .pricing">
    </section>
    <section class="actions">
      <button id="snapshot">Snapshot</button>
      <button id="inspect">Inspect</button>
      <button id="screenshot-button">Screenshot</button>
      <button id="clone-preview">Preview Clone</button>
      <button id="clone-region">Clone Selection</button>
      <button id="clone-page">Clone Page</button>
    </section>
    <img id="screenshot" alt="Browser screenshot" hidden>
    <pre id="output"></pre>
  </main>
  <script type="module">{BROWSER_BUNDLE}</script>
</body>
</html>
"""

BROWSER_HTML = BROWSER_HTML.replace("{BROWSER_BUNDLE}", BROWSER_BUNDLE)


def register_browser_app(apps: Apps) -> None:
    """Register the interactive browser MCP App."""

    @apps.tool(
        resource_uri=BROWSER_APP_URI,
        title="Open Sandbox Browser",
        description=(
            "Open a public http(s) URL in an isolated browser sandbox and show "
            "an interactive browser inspection and cloning UI."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    def browser_open(
        sandbox_name: str,
        url: str,
    ) -> dict[str, object]:
        """Open a URL in the isolated browser and initialize the browser App."""
        result = open_page(sandbox_name, url)
        result["sandbox_name"] = sandbox_name
        return result

    browser_domain = (
        os.environ.get("MCP_BROWSER_APP_DOMAIN", "").strip()
        or DEFAULT_BROWSER_APP_DOMAIN
    )

    apps.add_html_resource(
        BROWSER_APP_URI,
        BROWSER_HTML,
        title="Sandbox Browser",
        description="Isolated Chrome browser inspection and static cloning UI.",
        domain=browser_domain,
        csp=ResourceCsp(),
        prefers_border=True,
    )
