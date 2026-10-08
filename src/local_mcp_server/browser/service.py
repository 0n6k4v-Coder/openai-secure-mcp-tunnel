from __future__ import annotations

import base64
import ipaddress
import json
import subprocess
import urllib.parse
import uuid

from ..chrome_devtools.service import execute_chrome_devtools
from ..infrastructure.openshell.sandbox import execute_sandbox_argv
from ..sandbox.policy import validate_name

_MAX_URL_LENGTH = 2048
_MAX_SELECTOR_LENGTH = 2048
_MAX_SCRIPT_LENGTH = 16 * 1024
_MAX_SCREENSHOT_BYTES = 4 * 1024 * 1024
_MAX_INPUT_TEXT_LENGTH = 64 * 1024
_MAX_VIEWPORT_DIMENSION = 4096
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_PRIVATE_HOSTS = frozenset({"localhost", "localhost.localdomain", "0.0.0.0", "::1"})

_CDP_RELAY_PATH = "/tmp/mcp-browser-screencast-relay.js"
_CDP_INPUT_PATH = "/tmp/mcp-browser-input.js"
_CDP_INPUT_SOCKET_PREFIX = "/tmp/mcp-browser-input-"

class BrowserError(RuntimeError):
    """Raised when a browser operation cannot be completed."""


def validate_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise BrowserError("URL must not be empty.")
    url = url.strip()
    if len(url) > _MAX_URL_LENGTH:
        raise BrowserError(f"URL exceeds {_MAX_URL_LENGTH} characters.")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise BrowserError("Only http:// and https:// URLs are supported.")
    if not parsed.hostname:
        raise BrowserError("URL must contain a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise BrowserError("URLs containing embedded credentials are not allowed.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in _PRIVATE_HOSTS:
        raise BrowserError("Local or loopback browser targets are not allowed.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private or address.is_loopback or address.is_link_local
        or address.is_reserved or address.is_multicast
    ):
        raise BrowserError("Private, loopback, link-local, reserved, and multicast IP targets are not allowed.")
    return url


def validate_page_id(page_id: int) -> int:
    if isinstance(page_id, bool) or not isinstance(page_id, int) or page_id < 0:
        raise BrowserError("page_id must be a non-negative integer.")
    return page_id


def validate_selector(selector: str) -> str:
    if not isinstance(selector, str) or not selector.strip():
        raise BrowserError("selector must not be empty.")
    selector = selector.strip()
    if len(selector) > _MAX_SELECTOR_LENGTH:
        raise BrowserError(f"selector exceeds {_MAX_SELECTOR_LENGTH} characters.")
    return selector


def _parse_cli_output(result: dict[str, object]) -> object:
    if int(result.get("return_code", 1)) != 0:
        raise BrowserError(str(result.get("stderr") or result.get("stdout") or "Chrome DevTools command failed."))
    raw = result.get("stdout", "")
    if not isinstance(raw, str):
        return raw
    raw = raw.strip()
    if not raw:
        return None
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(outer, list) and outer and isinstance(outer[0], dict) and isinstance(outer[0].get("text"), str):
        text = outer[0]["text"]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return outer


def _run(sandbox_name: str, command: str, arguments: list[str] | None = None) -> object:
    sandbox_name = validate_name(sandbox_name)
    args = list(arguments or [])
    if "--output-format=json" not in args:
        args.append("--output-format=json")
    return _parse_cli_output(
        execute_chrome_devtools(sandbox_name=sandbox_name, command=command, arguments=args)
    )


_ALLOWED_ENDPOINTS_CACHE: set[tuple[str, str, int]] = set()
_CDP_INPUT_READY: set[str] = set()
_CDP_INPUT_SOCKET_READY: set[tuple[str, int]] = set()


def _ensure_browser_endpoint_allowed(sandbox_name: str, url: str) -> None:
    """Dynamically ensure the destination host for url is permitted in sandbox policy."""
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        if not host:
            return
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        cache_key = (sandbox_name, host, port)
        if cache_key in _ALLOWED_ENDPOINTS_CACHE:
            return

        cmd = [
            "openshell",
            "policy",
            "update",
            sandbox_name,
            "--add-endpoint",
            f"{host}:{port}",
            "--binary",
            "/opt/chrome/chrome",
            "--rule-name",
            "browser_web",
            "--wait",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            _ALLOWED_ENDPOINTS_CACHE.add(cache_key)

            parts = host.split(".")
            if len(parts) >= 2 and not all(p.isdigit() for p in parts):
                domain = (
                    ".".join(parts[-3:])
                    if len(parts) > 2 and parts[-2] in {"co", "com", "org", "net", "gov", "edu"}
                    else ".".join(parts[-2:])
                )
                wildcard_key = (sandbox_name, f"*.{domain}", port)
                if wildcard_key not in _ALLOWED_ENDPOINTS_CACHE:
                    subprocess.run(
                        [
                            "openshell",
                            "policy",
                            "update",
                            sandbox_name,
                            "--add-endpoint",
                            f"*.{domain}:{port}",
                            "--binary",
                            "/opt/chrome/chrome",
                            "--rule-name",
                            "browser_web",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    _ALLOWED_ENDPOINTS_CACHE.add(wildcard_key)
    except Exception:
        pass


def open_page(sandbox_name: str, url: str) -> dict[str, object]:
    url = validate_url(url)
    _ensure_browser_endpoint_allowed(sandbox_name, url)
    result = _run(sandbox_name, "new_page", [url])
    return {"url": url, "result": result}


def list_pages(sandbox_name: str) -> object:
    return _run(sandbox_name, "list_pages")


def navigate_page(sandbox_name: str, page_id: int, url: str) -> dict[str, object]:
    page_id = validate_page_id(page_id)
    url = validate_url(url)
    _ensure_browser_endpoint_allowed(sandbox_name, url)
    result = _run(sandbox_name, "navigate_page", [str(page_id), "--url", url])
    return {"page_id": page_id, "url": url, "result": result}


def take_snapshot(sandbox_name: str, page_id: int, verbose: bool = False) -> dict[str, object]:
    page_id = validate_page_id(page_id)
    args = [str(page_id)]
    if verbose:
        args.extend(["--verbose", "true"])
    result = _run(sandbox_name, "take_snapshot", args)
    return {"page_id": page_id, "snapshot": result}


def evaluate(sandbox_name: str, page_id: int, function: str) -> dict[str, object]:
    page_id = validate_page_id(page_id)
    if not isinstance(function, str) or not function.strip():
        raise BrowserError("function must not be empty.")
    function = function.strip()
    if len(function) > _MAX_SCRIPT_LENGTH:
        raise BrowserError(f"function exceeds {_MAX_SCRIPT_LENGTH} characters.")
    result = _run(sandbox_name, "evaluate_script", [function, "--pageId", str(page_id)])
    return {"page_id": page_id, "result": result}


browser_evaluate = evaluate


def screenshot(sandbox_name: str, page_id: int, *, full_page: bool = False) -> bytes:
    page_id = validate_page_id(page_id)
    path = f"/tmp/mcp-browser-{uuid.uuid4().hex}.png"
    args = [str(page_id), "--filePath", path, "--format", "jpeg", "--quality", "70"]
    if full_page:
        args.extend(["--fullPage", "true"])
    _run(sandbox_name, "take_screenshot", args)
    try:
        result = execute_sandbox_argv(validate_name(sandbox_name), ["base64", "-w", "0", path], timeout_seconds=30)
        if int(result.get("return_code", 1)) != 0:
            raise BrowserError(str(result.get("stderr") or "Unable to read screenshot."))
        encoded = result.get("stdout", "")
        if not isinstance(encoded, str):
            raise BrowserError("Screenshot data was invalid.")
        data = base64.b64decode(encoded, validate=True)
        if len(data) > _MAX_SCREENSHOT_BYTES:
            raise BrowserError("Screenshot exceeds the maximum allowed size.")
        return data
    finally:
        execute_sandbox_argv(validate_name(sandbox_name), ["rm", "-f", path], timeout_seconds=10)


def inspect_selector(sandbox_name: str, page_id: int, selector: str) -> dict[str, object]:
    selector = validate_selector(selector)
    script = """(selector) => {
      const element = document.querySelector(selector);
      if (!element) return {found: false, selector};
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        found: true, selector, tagName: element.tagName.toLowerCase(),
        id: element.id || null,
        className: typeof element.className === "string" ? element.className : null,
        text: (element.innerText || element.textContent || "").trim().slice(0, 4000),
        outerHTML: element.outerHTML.slice(0, 20000),
        bbox: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
        computed: {
          display: style.display, position: style.position, width: style.width,
          height: style.height, margin: style.margin, padding: style.padding,
          color: style.color, backgroundColor: style.backgroundColor, font: style.font,
        }
      };
    }"""
    result = evaluate(sandbox_name, page_id, f"({script}).bind(null, {json.dumps(selector)})")
    return result


def extract_clone_payload(
    sandbox_name: str,
    page_id: int,
    selector: str | None = None,
    *,
    metadata_only: bool = False,
) -> dict[str, object]:
    selector_json = json.dumps(selector) if selector is not None else "null"
    script = f"""() => {{
      const selector = {selector_json};
      const target = selector ? document.querySelector(selector) : document.documentElement;
      if (!target) return {{found: false, selector}};
      const clone = target.cloneNode(true);
      clone.querySelectorAll?.('script, noscript, iframe, object, embed').forEach(node => node.remove());
      clone.querySelectorAll?.('*').forEach(node => {{
        [...node.attributes].forEach(attr => {{
          if (attr.name.toLowerCase().startsWith('on') || attr.name.toLowerCase() === 'srcdoc') {{
            node.removeAttribute(attr.name);
          }}
        }});
      }});
      const styles = [];
      for (const sheet of document.styleSheets) {{
        try {{
          styles.push([...sheet.cssRules].map(rule => rule.cssText).join("\n"));
        }} catch (_) {{}}
      }}
      return {{
        found: true,
        selector,
        url: location.href,
        title: document.title,
        ...(metadata_only
          ? {{html_bytes: clone.outerHTML.length, css_bytes: styles.join("\n").length}}
          : {{html: clone.outerHTML, css: styles.join("\n")}}),
        externalStylesheets: [...document.querySelectorAll('link[rel~="stylesheet"]')].map(link => link.href),
        assets: [...document.querySelectorAll('img[src], source[src], video[src]')].map(node => node.src).filter(Boolean)
      }};
    }}"""
    return evaluate(sandbox_name, page_id, script)["result"]


def _validate_input_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        raise BrowserError("text must not be empty.")
    if len(text) > _MAX_INPUT_TEXT_LENGTH:
        raise BrowserError(f"text exceeds {_MAX_INPUT_TEXT_LENGTH} characters.")
    return text


def _validate_coordinate(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserError(f"{name} must be a number.")
    if value < 0 or value > _MAX_VIEWPORT_DIMENSION:
        raise BrowserError(f"{name} must be between 0 and {_MAX_VIEWPORT_DIMENSION}.")
    return float(value)


def _write_sandbox_file(sandbox_name: str, path: str, content: str) -> None:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    result = execute_sandbox_argv(
        validate_name(sandbox_name),
        ["sh", "-c", f"printf '%s' {json.dumps(encoded)} | base64 -d > {json.dumps(path)}"],
        timeout_seconds=10,
    )
    if int(result.get("return_code", 1)) != 0:
        raise BrowserError(str(result.get("stderr") or "Unable to prepare browser helper."))


_CDP_RELAY_SCRIPT = r"""
const fs = require("fs");
const net = require("net");
const pageId = Number(process.argv[2]);
const outputPath = process.argv[3];
const metadataPath = process.argv[4];
const width = Number(process.argv[5] || 1280);
const height = Number(process.argv[6] || 800);
const quality = Number(process.argv[7] || 70);
const inputSocketPath = process.argv[8];

async function pageTarget() {
  const response = await fetch("http://127.0.0.1:9222/json/list");
  const targets = await response.json();
  const pages = targets.filter((target) => target.type === "page");
  const target = pages[pageId - 1];
  if (!target?.webSocketDebuggerUrl) throw new Error("Unable to resolve browser page " + pageId);
  return target.webSocketDebuggerUrl;
}

function modifiers(payload) {
  let value = 0;
  if (payload.alt) value |= 1;
  if (payload.ctrl) value |= 2;
  if (payload.meta) value |= 4;
  if (payload.shift) value |= 8;
  return value;
}

function button(value) {
  return value === "right" ? "right" : value === "middle" ? "middle" : "left";
}

async function main() {
  fs.rmSync(inputSocketPath, {force: true});
  fs.writeFileSync(metadataPath, JSON.stringify({state: "starting"}));

  const ws = new WebSocket(await pageTarget());
  let commandId = 0;
  const pending = new Map();
  let wsReadyResolve;
  let wsReadyReject;
  const wsReady = new Promise((resolve, reject) => {
    wsReadyResolve = resolve;
    wsReadyReject = reject;
  });

  const send = (method, params) => {
    ws.send(JSON.stringify({id: ++commandId, method, params}));
  };

  const cdp = (method, params) => new Promise((resolve, reject) => {
    const id = ++commandId;
    pending.set(id, {resolve, reject});
    ws.send(JSON.stringify({id, method, params}));
    setTimeout(() => {
      const item = pending.get(id);
      if (item) {
        pending.delete(id);
        item.reject(new Error("CDP command timed out"));
      }
    }, 5000);
  });

  const executeInput = async (operation, payload) => {
    await wsReady;
    const x = Number(payload.x || 0);
    const y = Number(payload.y || 0);
    if (operation === "click") {
      const params = {x, y, button: button(payload.button), clickCount: payload.double ? 2 : 1, modifiers: modifiers(payload)};
      await cdp("Input.dispatchMouseEvent", {type: "mouseMoved", ...params, button: "none"});
      await cdp("Input.dispatchMouseEvent", {type: "mousePressed", ...params});
      await cdp("Input.dispatchMouseEvent", {type: "mouseReleased", ...params});
    } else if (operation === "move") {
      await cdp("Input.dispatchMouseEvent", {type: "mouseMoved", x, y, modifiers: modifiers(payload), button: "none"});
    } else if (operation === "scroll") {
      await cdp("Input.dispatchMouseEvent", {type: "mouseWheel", x, y, deltaX: Number(payload.deltaX || 0), deltaY: Number(payload.deltaY || 0), modifiers: modifiers(payload)});
    } else if (operation === "type") {
      await cdp("Input.insertText", {text: String(payload.text || "")});
    } else if (operation === "key") {
      const key = String(payload.key || "");
      const keyMap = {
        Enter: {key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13},
        Tab: {key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9},
        Backspace: {key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8, nativeVirtualKeyCode: 8},
        Escape: {key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27},
        ArrowUp: {key: "ArrowUp", code: "ArrowUp", windowsVirtualKeyCode: 38, nativeVirtualKeyCode: 38},
        ArrowDown: {key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40, nativeVirtualKeyCode: 40},
        ArrowLeft: {key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37, nativeVirtualKeyCode: 37},
        ArrowRight: {key: "ArrowRight", code: "ArrowRight", windowsVirtualKeyCode: 39, nativeVirtualKeyCode: 39},
        Space: {key: " ", code: "Space", windowsVirtualKeyCode: 32, nativeVirtualKeyCode: 32},
      };
      const parts = key.split("+");
      const mainKey = parts.pop();
      const flags = {ctrl: parts.includes("Control") || parts.includes("Ctrl"), shift: parts.includes("Shift"), alt: parts.includes("Alt"), meta: parts.includes("Meta") || parts.includes("Command") || parts.includes("Cmd")};
      const base = keyMap[mainKey] || {key: mainKey, code: mainKey.length === 1 ? "Key" + mainKey.toUpperCase() : mainKey};
      const params = {...base, modifiers: modifiers(flags), autoRepeat: false};
      await cdp("Input.dispatchKeyEvent", {type: "keyDown", ...params});
      if (!flags.ctrl && !flags.alt && !flags.meta && mainKey.length === 1) {
        await cdp("Input.dispatchKeyEvent", {type: "char", text: mainKey, key: mainKey, modifiers: modifiers(flags)});
      }
      await cdp("Input.dispatchKeyEvent", {type: "keyUp", ...params});
    } else if (operation === "drag") {
      const fromX = Number(payload.fromX), fromY = Number(payload.fromY), toX = Number(payload.toX), toY = Number(payload.toY);
      const b = button(payload.button);
      await cdp("Input.dispatchMouseEvent", {type: "mouseMoved", x: fromX, y: fromY, button: "none"});
      await cdp("Input.dispatchMouseEvent", {type: "mousePressed", x: fromX, y: fromY, button: b, clickCount: 1});
      const steps = Math.max(2, Number(payload.steps || 8));
      for (let i = 1; i <= steps; i++) {
        const t = i / steps;
        await cdp("Input.dispatchMouseEvent", {type: "mouseMoved", x: fromX + (toX - fromX) * t, y: fromY + (toY - fromY) * t, button: b, buttons: b === "left" ? 1 : b === "middle" ? 4 : 2});
      }
      await cdp("Input.dispatchMouseEvent", {type: "mouseReleased", x: toX, y: toY, button: b, clickCount: 1});
    } else {
      throw new Error("Unknown browser input operation: " + operation);
    }
  };

  let inputChain = Promise.resolve();
  const inputServer = net.createServer((connection) => {
    let buffer = "";
    connection.setEncoding("utf8");
    connection.on("data", (chunk) => {
      buffer += chunk;
      while (true) {
        const newline = buffer.indexOf("\n");
        if (newline < 0) break;
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (!line) continue;
        let request;
        try { request = JSON.parse(line); }
        catch (error) {
          connection.write(JSON.stringify({ok: false, error: "invalid request"}) + "\n");
          continue;
        }
        inputChain = inputChain.then(async () => {
          try {
            await executeInput(String(request.operation || ""), request.payload || {});
            connection.write(JSON.stringify({ok: true}) + "\n");
          } catch (error) {
            connection.write(JSON.stringify({ok: false, error: String(error)}) + "\n");
          }
        });
      }
    });
    connection.on("error", () => {});
  });

  await new Promise((resolve, reject) => {
    inputServer.once("error", reject);
    inputServer.listen(inputSocketPath, () => {
      inputServer.removeListener("error", reject);
      resolve();
    });
  });

  ws.onopen = async () => {
    await cdp("Page.enable", {});
    send("Page.startScreencast", {
      format: "jpeg",
      quality,
      maxWidth: width,
      maxHeight: height,
      everyNthFrame: 4,
      maxFramesInFlight: 1,
      sendLastFrame: true,
    });
    wsReadyResolve();
    fs.writeFileSync(metadataPath, JSON.stringify({state: "running", pageId, width, height, inputSocketPath}));
  };

  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.id != null) {
        const item = pending.get(message.id);
        if (item) {
          pending.delete(message.id);
          if (message.error) item.reject(new Error(JSON.stringify(message.error)));
          else item.resolve(message.result);
        }
      }
      if (message.method !== "Page.screencastFrame") return;
      const tempFramePath = outputPath + ".tmp";
      fs.writeFileSync(tempFramePath, Buffer.from(message.params.data, "base64"));
      fs.renameSync(tempFramePath, outputPath);
      send("Page.screencastFrameAck", {sessionId: message.params.sessionId});
    } catch (error) {
      fs.writeFileSync(metadataPath, JSON.stringify({state: "error", error: String(error)}));
    }
  };

  ws.onerror = (error) => {
    wsReadyReject(new Error(String(error)));
    fs.writeFileSync(metadataPath, JSON.stringify({state: "error", error: String(error)}));
    process.exitCode = 1;
  };

  ws.onclose = () => {
    try {
      inputServer.close();
      fs.rmSync(inputSocketPath, {force: true});
      fs.writeFileSync(metadataPath, JSON.stringify({state: "stopped"}));
    } finally {
      process.exit(0);
    }
  };
}

main().catch((error) => {
  fs.rmSync(inputSocketPath, {force: true});
  fs.writeFileSync(metadataPath, JSON.stringify({state: "error", error: String(error)}));
  process.exit(1);
});
"""

_CDP_INPUT_SCRIPT = r"""
const net = require("net");
const socketPath = process.argv[2];
const operation = process.argv[3];
const payload = process.argv[4] || "{}";
let attempts = 0;

function connect() {
  const socket = net.createConnection(socketPath);
  let buffer = "";
  socket.setEncoding("utf8");
  socket.on("connect", () => {
    socket.write(JSON.stringify({operation, payload: JSON.parse(payload)}) + "\n");
  });
  socket.on("data", (chunk) => {
    buffer += chunk;
    const newline = buffer.indexOf("\n");
    if (newline < 0) return;
    const response = JSON.parse(buffer.slice(0, newline));
    if (!response.ok) {
      console.error(response.error || "Browser input failed.");
      process.exitCode = 1;
    }
    socket.end();
  });
  socket.on("error", (error) => {
    if (error.code === "ENOENT" && attempts < 20) {
      attempts += 1;
      setTimeout(connect, 50);
      return;
    }
    console.error(String(error));
    process.exitCode = 1;
  });
}
connect();
"""


def _ensure_cdp_relay(sandbox_name: str) -> None:
    _write_sandbox_file(sandbox_name, _CDP_RELAY_PATH, _CDP_RELAY_SCRIPT)

def _ensure_cdp_input(sandbox_name: str) -> None:
    sandbox_name = validate_name(sandbox_name)
    if sandbox_name in _CDP_INPUT_READY:
        return
    _write_sandbox_file(sandbox_name, _CDP_INPUT_PATH, _CDP_INPUT_SCRIPT)
    _CDP_INPUT_READY.add(sandbox_name)

def _run_node_script(sandbox_name: str, script_path: str, args: list[str], *, timeout_seconds: int = 15) -> dict[str, object]:
    return execute_sandbox_argv(validate_name(sandbox_name), ["node", script_path, *args], timeout_seconds=timeout_seconds)

def _input_socket_path(page_id: int) -> str:
    return f"{_CDP_INPUT_SOCKET_PREFIX}{validate_page_id(page_id)}.sock"

def _run_cdp_input(sandbox_name: str, page_id: int, operation: str, payload: dict[str, object]) -> None:
    page_id = validate_page_id(page_id)
    socket_path = _input_socket_path(page_id)
    _ensure_cdp_input(sandbox_name)
    key = (sandbox_name, page_id)
    if key not in _CDP_INPUT_SOCKET_READY:
        socket_check = execute_sandbox_argv(
            validate_name(sandbox_name),
            ["sh", "-c", f"test -S {json.dumps(socket_path)}"],
            timeout_seconds=5,
        )
        if int(socket_check.get("return_code", 1)) != 0:
            viewport_start(sandbox_name, page_id)
        _CDP_INPUT_SOCKET_READY.add(key)
    result = _run_node_script(
        sandbox_name,
        _CDP_INPUT_PATH,
        [socket_path, operation, json.dumps(payload, separators=(",", ":"))],
        timeout_seconds=10,
    )
    if int(result.get("return_code", 1)) != 0:
        _CDP_INPUT_SOCKET_READY.discard(key)
        viewport_start(sandbox_name, page_id)
        result = _run_node_script(
            sandbox_name,
            _CDP_INPUT_PATH,
            [socket_path, operation, json.dumps(payload, separators=(",", ":"))],
            timeout_seconds=10,
        )
        if int(result.get("return_code", 1)) == 0:
            _CDP_INPUT_SOCKET_READY.add(key)
    if int(result.get("return_code", 1)) != 0:
        raise BrowserError(str(result.get("stderr") or result.get("stdout") or "Browser input failed."))

def _viewport_paths(page_id: int) -> tuple[str, str, str, str]:
    token = str(validate_page_id(page_id))
    return (
        f"/tmp/mcp-browser-screencast-{token}.jpg",
        f"/tmp/mcp-browser-screencast-{token}.json",
        f"/tmp/mcp-browser-screencast-{token}.pid",
        f"/tmp/mcp-browser-screencast-{token}.log",
    )

def viewport_start(sandbox_name: str, page_id: int, *, width: int = 1280, height: int = 800, quality: int = 70) -> dict[str, object]:
    page_id = validate_page_id(page_id)
    if not isinstance(width, int) or not 320 <= width <= _MAX_VIEWPORT_DIMENSION:
        raise BrowserError("width must be an integer between 320 and 4096.")
    if not isinstance(height, int) or not 240 <= height <= _MAX_VIEWPORT_DIMENSION:
        raise BrowserError("height must be an integer between 240 and 4096.")
    if not isinstance(quality, int) or not 20 <= quality <= 90:
        raise BrowserError("quality must be an integer between 20 and 90.")
    sandbox_name = validate_name(sandbox_name)
    _ensure_cdp_input(sandbox_name)
    _ensure_cdp_relay(sandbox_name)
    output_path, metadata_path, pid_path, log_path = _viewport_paths(page_id)
    socket_path = _input_socket_path(page_id)
    execute_sandbox_argv(sandbox_name, ["sh", "-c", f"if test -f {pid_path}; then kill $(cat {pid_path}) 2>/dev/null || true; fi; rm -f {json.dumps(socket_path)}"], timeout_seconds=10)
    command = (
        f"nohup node {_CDP_RELAY_PATH} {page_id} {json.dumps(output_path)} {json.dumps(metadata_path)} "
        f"{width} {height} {quality} {json.dumps(socket_path)} >{json.dumps(log_path)} 2>&1 & echo $! > {json.dumps(pid_path)}"
    )
    result = execute_sandbox_argv(sandbox_name, ["sh", "-c", command], timeout_seconds=10)
    if int(result.get("return_code", 1)) != 0:
        raise BrowserError(str(result.get("stderr") or "Unable to start browser screencast."))
    _CDP_INPUT_SOCKET_READY.add((sandbox_name, page_id))
    return {"sandbox_name": sandbox_name, "page_id": page_id, "width": width, "height": height, "quality": quality, "state": "starting"}

def viewport_frame(sandbox_name: str, page_id: int) -> tuple[bytes, str | None]:
    page_id = validate_page_id(page_id)
    sandbox_name = validate_name(sandbox_name)
    output_path, _, _, _ = _viewport_paths(page_id)
    result = execute_sandbox_argv(sandbox_name, ["sh", "-c", f"test -s {output_path} && base64 -w 0 {output_path} || true"], timeout_seconds=15)
    if int(result.get("return_code", 1)) != 0:
        raise BrowserError(str(result.get("stderr") or "Unable to read browser frame."))
    encoded = result.get("stdout", "")
    if not isinstance(encoded, str) or not encoded.strip():
        return b"", None
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise BrowserError("Browser screencast frame was invalid.") from exc
    if len(data) > _MAX_SCREENSHOT_BYTES:
        raise BrowserError("Browser screencast frame exceeds the maximum allowed size.")
    return data, "image/jpeg"

def viewport_stop(sandbox_name: str, page_id: int) -> dict[str, object]:
    page_id = validate_page_id(page_id)
    sandbox_name = validate_name(sandbox_name)
    _, _, pid_path, _ = _viewport_paths(page_id)
    socket_path = _input_socket_path(page_id)
    result = execute_sandbox_argv(sandbox_name, ["sh", "-c", f"if test -f {pid_path}; then kill $(cat {pid_path}) 2>/dev/null || true; rm -f {pid_path}; fi; rm -f {json.dumps(socket_path)}"], timeout_seconds=10)
    if int(result.get("return_code", 1)) != 0:
        raise BrowserError(str(result.get("stderr") or "Unable to stop browser screencast."))
    _CDP_INPUT_SOCKET_READY.discard((sandbox_name, page_id))
    return {"sandbox_name": sandbox_name, "page_id": page_id, "state": "stopped"}

def browser_click(sandbox_name: str, page_id: int, x: float, y: float, *, button_name: str = "left", double: bool = False) -> dict[str, object]:
    if button_name not in {"left", "middle", "right"}: raise BrowserError("button_name must be left, middle, or right.")
    _run_cdp_input(sandbox_name, page_id, "click", {"x": _validate_coordinate(x, "x"), "y": _validate_coordinate(y, "y"), "button": button_name, "double": double})
    return {"page_id": validate_page_id(page_id), "x": x, "y": y, "button": button_name, "double": double}

def browser_move(sandbox_name: str, page_id: int, x: float, y: float) -> dict[str, object]:
    _run_cdp_input(sandbox_name, page_id, "move", {"x": _validate_coordinate(x, "x"), "y": _validate_coordinate(y, "y")})
    return {"page_id": validate_page_id(page_id), "x": x, "y": y}

def browser_scroll(sandbox_name: str, page_id: int, delta_x: float, delta_y: float, *, x: float = 1, y: float = 1) -> dict[str, object]:
    _run_cdp_input(sandbox_name, page_id, "scroll", {"x": _validate_coordinate(x, "x"), "y": _validate_coordinate(y, "y"), "deltaX": delta_x, "deltaY": delta_y})
    return {"page_id": validate_page_id(page_id), "delta_x": delta_x, "delta_y": delta_y}

def browser_type(sandbox_name: str, page_id: int, text: str) -> dict[str, object]:
    text = _validate_input_text(text)
    _run_cdp_input(sandbox_name, page_id, "type", {"text": text})
    return {"page_id": validate_page_id(page_id), "text_length": len(text)}

def browser_key(sandbox_name: str, page_id: int, key: str) -> dict[str, object]:
    key = _validate_input_text(key)
    if len(key) > 128: raise BrowserError("key exceeds 128 characters.")
    _run_cdp_input(sandbox_name, page_id, "key", {"key": key})
    return {"page_id": validate_page_id(page_id), "key": key}

def browser_drag(sandbox_name: str, page_id: int, from_x: float, from_y: float, to_x: float, to_y: float, *, steps: int = 8) -> dict[str, object]:
    if not isinstance(steps, int) or not 2 <= steps <= 64: raise BrowserError("steps must be an integer between 2 and 64.")
    _run_cdp_input(sandbox_name, page_id, "drag", {"fromX": _validate_coordinate(from_x, "from_x"), "fromY": _validate_coordinate(from_y, "from_y"), "toX": _validate_coordinate(to_x, "to_x"), "toY": _validate_coordinate(to_y, "to_y"), "steps": steps})
    return {"page_id": validate_page_id(page_id), "from": [from_x, from_y], "to": [to_x, to_y], "steps": steps}
