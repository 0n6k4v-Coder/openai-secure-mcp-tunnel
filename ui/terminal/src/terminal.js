import "@xterm/xterm/css/xterm.css";
import { App } from "@modelcontextprotocol/ext-apps";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";

const app = new App({ name: "Sandbox Terminal", version: "1.0.0", autoResize: true });
const terminal = new Terminal({
  cursorBlink: true,
  convertEol: false,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
  fontSize: 13,
  scrollback: 5000,
  theme: { background: "#000000", foreground: "#d7dee7", cursor: "#ffffff" },
});
const fitAddon = new FitAddon();
terminal.loadAddon(fitAddon);
terminal.open(document.getElementById("terminal"));

let terminalId = null;
let polling = false;
let closed = false;
const status = document.getElementById("status");
const statusText = document.getElementById("status-text");

function setStatus(text, state = "") {
  statusText.textContent = text;
  status.className = state;
}
function showError(message) {
  setStatus("Error", "error");
  terminal.write("\r\n\x1b[31m[terminal error] " + String(message).replaceAll("\r","").replaceAll("\n"," ") + "\x1b[0m\r\n");
}
function getStructuredContent(result) {
  if (!result) return null;
  if (result.structuredContent) return result.structuredContent;
  if (result.structured_content) return result.structured_content;
  if (result.result?.structuredContent) return result.result.structuredContent;
  if (result.result?.structured_content) return result.result.structured_content;
  const contentList = result.content ?? result.result?.content;
  if (Array.isArray(contentList)) {
    for (const item of contentList) {
      if (item?.type === "text" && typeof item.text === "string") {
        try { const parsed = JSON.parse(item.text); if (parsed && typeof parsed === "object") return parsed; } catch {}
      }
    }
  }
  return null;
}
async function initializeSession(state) {
  if (!state?.terminal_id || terminalId) return;
  terminalId = state.terminal_id;
  setStatus("Connected", "connected");
  terminal.clear();
  terminal.focus();
  if (state.output) terminal.write(state.output);
  await resizeTerminal();
  window.setInterval(() => void pollOutput(), 200);
  void pollOutput();
}
async function callServerTool(name, arguments_) {
  let result;
  if (typeof app?.callServerTool === "function") {
    result = await app.callServerTool({ name, arguments: arguments_ });
  } else if (typeof window.openai?.callTool === "function") {
    result = await window.openai.callTool(name, arguments_);
  } else {
    throw new Error("No tool execution bridge available in host environment.");
  }
  if (result.isError) {
    const message = result.content?.map((block) => block?.text ?? "").filter(Boolean).join("\n") || `Tool ${name} failed`;
    throw new Error(message);
  }
  return result;
}
async function pollOutput() {
  if (!terminalId || polling || closed) return;
  polling = true;
  try {
    const result = await callServerTool("terminal_state", { terminal_id: terminalId, clear_buffer: true });
    const state = getStructuredContent(result);
    if (!state) return;
    if (state.output) terminal.write(state.output);
    if (state.status === "terminated") { closed = true; setStatus("Exited"); }
    else if (state.error) showError(state.error);
  } catch (error) { if (!closed) showError(error); }
  finally { polling = false; }
}
async function resizeTerminal() {
  if (!terminalId || closed) return;
  fitAddon.fit();
  const cols = terminal.cols, rows = terminal.rows;
  if (!cols || !rows) return;
  try { await callServerTool("terminal_resize", { terminal_id: terminalId, cols, rows }); }
  catch (error) { showError(error); }
}
app.ontoolresult = async (params) => {
  const state = getStructuredContent(params);
  if (state) await initializeSession(state);
};
terminal.onData(async (data) => {
  if (!terminalId || closed) return;
  try { await callServerTool("terminal_input", { terminal_id: terminalId, data }); }
  catch (error) { showError(error); }
});
terminal.onResize(({ cols, rows }) => {
  if (!terminalId || closed) return;
  void callServerTool("terminal_resize", { terminal_id: terminalId, cols, rows }).catch(showError);
});
window.addEventListener("resize", () => { if (!terminalId || closed) return; fitAddon.fit(); });
app.onteardown = async () => {
  if (!terminalId || closed) return {};
  closed = true;
  try { await callServerTool("terminal_close", { terminal_id: terminalId }); } catch {}
  return {};
};
window.addEventListener("message", async (event) => {
  const data = event.data;
  if (!data) return;
  if (data.terminal_id) await initializeSession(data);
  else if (data.params) { const state = getStructuredContent(data.params); if (state?.terminal_id) await initializeSession(state); }
  else if (data.result) { const state = getStructuredContent(data.result); if (state?.terminal_id) await initializeSession(state); }
});

try {
  fitAddon.fit();
  const CONNECT_TIMEOUT_MS = 5000;
  await Promise.race([
    app.connect(),
    new Promise((_, reject) => setTimeout(() => reject(new Error("MCP Apps bridge connection timed out after 5 seconds")), CONNECT_TIMEOUT_MS)),
  ]);
  setStatus("Ready");
  terminal.focus();
  let attempts = 0;
  const discoveryInterval = setInterval(async () => {
    if (terminalId || closed || attempts >= 20) {
      clearInterval(discoveryInterval);
      if (!terminalId && !closed) {
        setStatus("Ready (Click to Connect)");
        terminal.write("\r\n\x1b[33m[Click or press Enter to attach to active terminal session]\x1b[0m\r\n");
      }
      return;
    }
    attempts++;
    try {
      const listRes = await callServerTool("terminal_list", {});
      const listState = getStructuredContent(listRes);
      const sessions = Array.isArray(listState) ? listState : (Array.isArray(listState?.result) ? listState.result : []);
      const activeSession = sessions.find((s) => s?.status === "active") || sessions[0];
      if (activeSession?.terminal_id) { clearInterval(discoveryInterval); await initializeSession(activeSession); }
    } catch (err) { console.debug("[discovery attempt failed]", err); }
  }, 500);
  terminal.onKey(async () => {
    if (!terminalId) {
      try {
        const listRes = await callServerTool("terminal_list", {});
        const listState = getStructuredContent(listRes);
        const sessions = Array.isArray(listState) ? listState : (Array.isArray(listState?.result) ? listState.result : []);
        const activeSession = sessions.find((s) => s?.status === "active") || sessions[0];
        if (activeSession?.terminal_id) await initializeSession(activeSession);
      } catch (e) { showError("Could not attach: " + e.message); }
    }
  });
} catch (error) {
  showError(error);
}
