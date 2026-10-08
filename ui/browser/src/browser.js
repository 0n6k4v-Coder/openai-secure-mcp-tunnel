import { App } from "@modelcontextprotocol/ext-apps";

const app = new App({ name: "Sandbox Browser", version: "0.1.0" });
const $ = (id) => document.getElementById(id);
const status = $("status");
const urlInput = $("url");
const pageInput = $("page");
const selectorInput = $("selector");
const output = $("output");
const screenshot = $("screenshot");

function setStatus(message, kind = "") {
  status.textContent = message;
  status.dataset.kind = kind;
}

function getStructured(result) {
  if (!result) return null;
  for (const key of ["structuredContent", "structured_content"]) {
    if (result[key] != null) return result[key];
  }
  for (const item of result.content || []) {
    if (item.type === "text") {
      try { return JSON.parse(item.text); } catch (_) {}
    }
  }
  return null;
}

async function call(name, args) {
  if (typeof app.callServerTool === "function") {
    return app.callServerTool({ name, arguments: args });
  }
  if (window.openai?.callTool) return window.openai.callTool(name, args);
  throw new Error("MCP Apps tool bridge is unavailable.");
}

function show(value) {
  output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

async function openUrl() {
  const url = urlInput.value.trim();
  if (!url) return;
  setStatus("Opening…");
  try {
    const result = await call("browser_open", { sandbox_name: window.__browserSandbox, url });
    const data = getStructured(result);
    show(data);
    const nested = data && data.result;
    const pageId = (nested && (nested.pageId ?? nested.page_id)) ?? (data && data.page_id);
    if (Number.isInteger(pageId)) pageInput.value = String(pageId);
    setStatus("Opened", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function snapshotCall() {
  const pageId = Number(pageInput.value);
  if (!Number.isInteger(pageId)) return;
  setStatus("Inspecting…");
  try {
    const result = await call("browser_snapshot", {
      sandbox_name: window.__browserSandbox, page_id: pageId
    });
    show(getStructured(result) ?? result);
    setStatus("Snapshot ready", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function inspectCall() {
  const pageId = Number(pageInput.value);
  const selector = selectorInput.value.trim();
  if (!Number.isInteger(pageId) || !selector) return;
  setStatus("Inspecting element…");
  try {
    const result = await call("browser_inspect", {
      sandbox_name: window.__browserSandbox, page_id: pageId, selector
    });
    show(getStructured(result) ?? result);
    setStatus("Element inspected", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function screenshotCall() {
  const pageId = Number(pageInput.value);
  if (!Number.isInteger(pageId)) return;
  setStatus("Capturing…");
  try {
    const result = await call("browser_screenshot", {
      sandbox_name: window.__browserSandbox, page_id: pageId, full_page: false
    });
    const image = (result?.content || []).find((item) => item.type === "image");
    if (image?.data) {
      screenshot.src = "data:" + (image.mimeType || image.mime_type || "image/png") + ";base64," + image.data;
      screenshot.hidden = false;
    }
    setStatus("Screenshot ready", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function clonePreview() {
  const pageId = Number(pageInput.value);
  const selector = selectorInput.value.trim() || null;
  if (!Number.isInteger(pageId)) return;
  setStatus("Preparing clone preview…");
  try {
    const result = await call("clone_preview", {
      sandbox_name: window.__browserSandbox, page_id: pageId, selector
    });
    show(getStructured(result) ?? result);
    setStatus("Clone preview ready", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function cloneRegion() {
  const pageId = Number(pageInput.value);
  const selector = selectorInput.value.trim();
  if (!Number.isInteger(pageId) || !selector) return;
  setStatus("Cloning selection…");
  try {
    const result = await call("clone_region", {
      sandbox_name: window.__browserSandbox, page_id: pageId, selector
    });
    show(getStructured(result) ?? result);
    setStatus("Region cloned", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function clonePage() {
  const pageId = Number(pageInput.value);
  if (!Number.isInteger(pageId)) return;
  setStatus("Cloning page…");
  try {
    const result = await call("clone_page", {
      sandbox_name: window.__browserSandbox, page_id: pageId
    });
    show(getStructured(result) ?? result);
    setStatus("Page cloned", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

app.ontoolresult = (result) => {
  const data = getStructured(result);
  if (data?.sandbox_name) window.__browserSandbox = data.sandbox_name;
};

$("open").onclick = openUrl;
$("snapshot").onclick = snapshotCall;
$("inspect").onclick = inspectCall;
$("screenshot-button").onclick = screenshotCall;
const clonePreviewButton = $("clone-preview");
if (clonePreviewButton) clonePreviewButton.onclick = clonePreview;
$("clone-region").onclick = cloneRegion;
$("clone-page").onclick = clonePage;

try {
  await app.connect();
  setStatus("Ready", "ok");
} catch (error) {
  setStatus("Bridge error: " + (error.message || error), "error");
}
