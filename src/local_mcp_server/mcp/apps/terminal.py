from __future__ import annotations

from mcp.server.apps import Apps

TERMINAL_APP_URI = "ui://terminal/view"

TERMINAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Sandbox Live Terminal</title>
  <style>
    body {
      margin: 0;
      padding: 12px;
      background: #1e1e1e;
      color: #cccccc;
      font-family: Menlo, Monaco, "Courier New", monospace;
      font-size: 13px;
    }
    #header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 8px;
      border-bottom: 1px solid #333;
      margin-bottom: 8px;
    }
    .badge {
      background: #007acc;
      color: #fff;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 11px;
    }
    #term-screen {
      background: #000;
      color: #0f0;
      padding: 10px;
      border-radius: 4px;
      height: 380px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-all;
    }
    #input-bar {
      display: flex;
      margin-top: 8px;
      gap: 6px;
    }
    #term-input {
      flex: 1;
      background: #252526;
      border: 1px solid #3c3c3c;
      color: #fff;
      padding: 6px 8px;
      border-radius: 3px;
      font-family: inherit;
      font-size: 13px;
    }
    button {
      background: #0e639c;
      color: white;
      border: none;
      padding: 6px 12px;
      border-radius: 3px;
      cursor: pointer;
    }
    button:hover {
      background: #1177bb;
    }
  </style>
</head>
<body>
  <div id="header">
    <div><strong>Sandbox Terminal</strong> <span id="status-badge" class="badge">Connecting</span></div>
    <div id="terminal-meta" style="font-size: 11px; color: #888;">Live OpenShell PTY</div>
  </div>
  <div id="term-screen">$ Connecting to sandbox shell...</div>
  <div id="input-bar">
    <input id="term-input" type="text" placeholder="Type command or input and press Enter..." autofocus />
    <button id="send-btn">Send</button>
  </div>

  <script>
    const termScreen = document.getElementById("term-screen");
    const termInput = document.getElementById("term-input");
    const sendBtn = document.getElementById("send-btn");
    const statusBadge = document.getElementById("status-badge");

    let terminalId = null;
    let pollInterval = null;

    function appendOutput(text) {
      if (!text) return;
      termScreen.textContent += text;
      termScreen.scrollTop = termScreen.scrollHeight;
    }

    async function sendInput(val) {
      if (!terminalId) return;
      try {
        await window.openai?.callTool?.("terminal_input", {
          terminal_id: terminalId,
          data: val + "\\n"
        });
      } catch (err) {
        console.error("Failed to send terminal input:", err);
      }
    }

    async function pollOutput() {
      if (!terminalId) return;
      try {
        const res = await window.openai?.callTool?.("terminal_state", {
          terminal_id: terminalId,
          clear_buffer: true
        });
        if (res && res.output) {
          appendOutput(res.output);
        }
      } catch (err) {
        console.error("Poll error:", err);
      }
    }

    sendBtn.addEventListener("click", () => {
      const val = termInput.value;
      if (val) {
        sendInput(val);
        termInput.value = "";
      }
    });

    termInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = termInput.value;
        sendInput(val);
        termInput.value = "";
      }
    });

    window.addEventListener("message", (event) => {
      if (event.data && event.data.terminal_id) {
        terminalId = event.data.terminal_id;
        statusBadge.textContent = "Connected";
        statusBadge.style.background = "#388a34";
        pollInterval = setInterval(pollOutput, 500);
      }
    });
  </script>
</body>
</html>
"""


def register_terminal_app(apps: Apps) -> None:
    """Register the Terminal MCP App HTML resource."""
    apps.add_html_resource(
        TERMINAL_APP_URI,
        TERMINAL_HTML,
    )
