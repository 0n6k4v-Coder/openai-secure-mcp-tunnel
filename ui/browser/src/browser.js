import { App } from "@modelcontextprotocol/ext-apps";

const app = new App({ name: "Sandbox Browser", version: "0.2.0" });
const $ = (id) => document.getElementById(id);
const status = $("status");
const urlInput = $("url");
const pageInput = $("page");
const selectorInput = $("selector");
const output = $("output");
const viewport = $("viewport");

let frameBusy = false;
let pollTimer = null;
let inputChain = Promise.resolve();
let pointer = null;
let moveAt = 0;
let pendingMove = null;
let moveTimer = null;
let moveBusy = false;
let pendingWheel = null;
let wheelBusy = false;

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

function pageId() {
  const value = Number(pageInput.value);
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function viewportPoint(event) {
  const rect = viewport.getBoundingClientRect();
  const naturalWidth = viewport.naturalWidth || rect.width;
  const naturalHeight = viewport.naturalHeight || rect.height;
  return {
    x: Math.max(0, Math.min(naturalWidth, (event.clientX - rect.left) * naturalWidth / rect.width)),
    y: Math.max(0, Math.min(naturalHeight, (event.clientY - rect.top) * naturalHeight / rect.height)),
  };
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

async function pollFrame() {
  if (frameBusy) return;
  const id = pageId();
  if (id == null || !window.__browserSandbox) return;
  frameBusy = true;
  try {
    const result = await call("browser_viewport_frame", {
      sandbox_name: window.__browserSandbox,
      page_id: id,
    });
    const image = (result?.content || []).find((item) => item.type === "image");
    if (image?.data) {
      const mime = image.mimeType || image.mime_type || "image/jpeg";
      viewport.src = "data:" + mime + ";base64," + image.data;
      viewport.hidden = false;
    }
  } catch (error) {
    setStatus("Viewport: " + (error.message || error), "error");
  } finally {
    frameBusy = false;
  }
}

function startPolling() {
  stopPolling();
  pollFrame();
  pollTimer = setInterval(pollFrame, 90);
}

async function startViewport() {
  const id = pageId();
  if (id == null || !window.__browserSandbox) return;
  await call("browser_viewport_start", {
    sandbox_name: window.__browserSandbox,
    page_id: id,
    width: 1280,
    height: 800,
    quality: 62,
  });
  startPolling();
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
    const pages = (nested && Array.isArray(nested.pages)) ? nested.pages : (Array.isArray(data?.pages) ? data.pages : []);
    const selectedPage = pages.find((p) => p && p.selected) || (pages.length ? pages[pages.length - 1] : null);
    const id = (data && data.page_id) ?? (nested && (nested.pageId ?? nested.page_id)) ?? (selectedPage && selectedPage.id);
    if (Number.isInteger(id)) pageInput.value = String(id);
    if (data?.sandbox_name) window.__browserSandbox = data.sandbox_name;
    await startViewport();
    setStatus("Live", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function snapshotCall() {
  const id = pageId();
  if (id == null) return;
  setStatus("Inspecting…");
  try {
    const result = await call("browser_snapshot", { sandbox_name: window.__browserSandbox, page_id: id });
    show(getStructured(result) ?? result);
    setStatus("Snapshot ready", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function inspectCall() {
  const id = pageId();
  const selector = selectorInput.value.trim();
  if (id == null || !selector) return;
  setStatus("Inspecting element…");
  try {
    const result = await call("browser_inspect", { sandbox_name: window.__browserSandbox, page_id: id, selector });
    show(getStructured(result) ?? result);
    setStatus("Element inspected", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function screenshotCall() {
  const id = pageId();
  if (id == null) return;
  setStatus("Capturing…");
  try {
    const result = await call("browser_screenshot", { sandbox_name: window.__browserSandbox, page_id: id, full_page: false });
    const image = (result?.content || []).find((item) => item.type === "image");
    if (image?.data) {
      viewport.src = "data:" + (image.mimeType || image.mime_type || "image/jpeg") + ";base64," + image.data;
      viewport.hidden = false;
    }
    setStatus("Screenshot ready", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function clonePreview() {
  const id = pageId();
  if (id == null) return;
  const selector = selectorInput.value.trim() || null;
  setStatus("Preparing clone preview…");
  try {
    const result = await call("clone_preview", { sandbox_name: window.__browserSandbox, page_id: id, selector });
    show(getStructured(result) ?? result);
    setStatus("Clone preview ready", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function cloneRegion() {
  const id = pageId();
  const selector = selectorInput.value.trim();
  if (id == null || !selector) return;
  setStatus("Cloning selection…");
  try {
    const result = await call("clone_region", { sandbox_name: window.__browserSandbox, page_id: id, selector });
    show(getStructured(result) ?? result);
    setStatus("Region cloned", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

async function clonePage() {
  const id = pageId();
  if (id == null) return;
  setStatus("Cloning page…");
  try {
    const result = await call("clone_page", { sandbox_name: window.__browserSandbox, page_id: id });
    show(getStructured(result) ?? result);
    setStatus("Page cloned", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
    show(error.message || String(error));
  }
}

function sendInput(name, args) {
  const id = pageId();
  if (id == null) return inputChain;
  inputChain = inputChain.then(async () => {
    await call(name, { sandbox_name: window.__browserSandbox, page_id: id, ...args });
  }).catch((error) => {
    setStatus(error.message || String(error), "error");
  });
  return inputChain;
}

async function sendRealtimeInput(name, args) {
  const id = pageId();
  if (id == null) return;
  try {
    await call(name, { sandbox_name: window.__browserSandbox, page_id: id, ...args });
  } catch (error) {
    setStatus(error.message || String(error), "error");
  }
}

function queueMove(point) {
  pendingMove = point;
  if (moveTimer || moveBusy) return;
  moveTimer = setTimeout(flushMove, 60);
}

async function flushMove() {
  moveTimer = null;
  if (moveBusy || !pendingMove) return;
  const point = pendingMove;
  pendingMove = null;
  moveBusy = true;
  try {
    await sendRealtimeInput("browser_move", { ...point, button_name: pointer ? "left" : "none", buttons: pointer ? 1 : 0 });
  } finally {
    moveBusy = false;
    if (pendingMove) queueMove(pendingMove);
  }
}

function queueWheel(point, deltaX, deltaY) {
  if (pendingWheel) {
    pendingWheel.deltaX += deltaX;
    pendingWheel.deltaY += deltaY;
    pendingWheel.x = point.x;
    pendingWheel.y = point.y;
  } else {
    pendingWheel = { x: point.x, y: point.y, deltaX, deltaY };
  }
  if (wheelBusy) return;
  flushWheel();
}

async function flushWheel() {
  if (wheelBusy || !pendingWheel) return;
  const wheel = pendingWheel;
  pendingWheel = null;
  wheelBusy = true;
  try {
    await sendRealtimeInput("browser_scroll", {
      x: wheel.x, y: wheel.y, delta_x: Math.round(wheel.deltaX), delta_y: Math.round(wheel.deltaY),
    });
  } finally {
    wheelBusy = false;
    if (pendingWheel) {
      setTimeout(flushWheel, 20);
    }
  }
}

viewport.addEventListener("pointerdown", (event) => {
  viewport.focus();
  const point = viewportPoint(event);
  pointer = { ...point, clientX: event.clientX, clientY: event.clientY, moved: false, pointerId: event.pointerId, sentDown: false };
  viewport.setPointerCapture?.(event.pointerId);
});

viewport.addEventListener("pointermove", (event) => {
  const point = viewportPoint(event);
  if (!pointer) {
    // When no button is held, throttle hover move to at least 150ms to keep relay free
    const now = performance.now();
    if (now - moveAt > 150) {
      moveAt = now;
      queueMove(point);
    }
    return;
  }

  const dx = event.clientX - pointer.clientX;
  const dy = event.clientY - pointer.clientY;
  if (!pointer.moved && Math.hypot(dx, dy) > 5) {
    pointer.moved = true;
    pointer.sentDown = true;
    sendInput("browser_pointer_down", { x: pointer.x, y: pointer.y });
  }

  if (pointer.sentDown) {
    const now = performance.now();
    if (now - moveAt > 60) {
      moveAt = now;
      queueMove(point);
    }
  }
});

viewport.addEventListener("pointerup", async (event) => {
  const point = viewportPoint(event);
  const start = pointer;
  pointer = null;
  if (start?.pointerId != null) viewport.releasePointerCapture?.(start.pointerId);

  if (start && start.sentDown) {
    await sendInput("browser_pointer_up", { x: point.x, y: point.y });
  } else {
    // Fast path: Atomic click (single roundtrip instead of pointer_down + pointer_up)
    const clickPoint = start || point;
    await sendInput("browser_click", { x: clickPoint.x, y: clickPoint.y, button_name: "left" });
  }
  // Schedule an immediate frame poll to show the effect of the click without waiting for next tick
  setTimeout(pollFrame, 50);
});

viewport.addEventListener("pointercancel", async (event) => {
  const point = viewportPoint(event);
  const start = pointer;
  pointer = null;
  if (start?.pointerId != null) viewport.releasePointerCapture?.(start.pointerId);
  if (start?.sentDown) {
    await sendInput("browser_pointer_up", { x: point.x, y: point.y });
  }
});

viewport.addEventListener("wheel", (event) => {
  event.preventDefault();
  const point = viewportPoint(event);
  queueWheel(point, event.deltaX, event.deltaY);
}, { passive: false });

viewport.addEventListener("keydown", async (event) => {
  event.preventDefault();
  const modifiers = [];
  if (event.ctrlKey) modifiers.push("Control");
  if (event.shiftKey) modifiers.push("Shift");
  if (event.altKey) modifiers.push("Alt");
  if (event.metaKey) modifiers.push("Meta");
  const printable = event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey;
  if (printable) {
    await sendInput("browser_type", { text: event.key });
  } else {
    await sendInput("browser_key", { key: [...modifiers, event.key].join("+") });
  }
});

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
