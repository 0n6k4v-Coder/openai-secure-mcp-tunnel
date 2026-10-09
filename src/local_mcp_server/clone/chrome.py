from __future__ import annotations

import base64
import ipaddress
import json
import logging
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
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_PRIVATE_HOSTS = frozenset({"localhost", "localhost.localdomain", "0.0.0.0", "::1"})

_ALLOWED_ENDPOINTS_CACHE: set[tuple[str, str, int]] = set()

_log = logging.getLogger(__name__)


class BrowserError(RuntimeError):
    """Raised when a browser or DevTools operation cannot be completed."""


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
    if isinstance(outer, dict) and isinstance(outer.get("message"), str):
        msg = outer["message"]
        if "```json" in msg:
            parts = msg.split("```json", 1)[1].split("```", 1)
            if parts:
                try:
                    return json.loads(parts[0].strip())
                except json.JSONDecodeError:
                    pass
    return outer


def _run(sandbox_name: str, command: str, arguments: list[str] | None = None) -> object:
    sandbox_name = validate_name(sandbox_name)
    args = list(arguments or [])
    if "--output-format=json" not in args:
        args.append("--output-format=json")
    return _parse_cli_output(
        execute_chrome_devtools(sandbox_name=sandbox_name, command=command, arguments=args)
    )


def _ensure_browser_endpoint_allowed(sandbox_name: str, url: str) -> None:
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
    result = None
    try:
        result = _run(sandbox_name, "new_page", [url])
    except Exception as exc:
        result = str(exc)

    page_id = None
    if isinstance(result, dict):
        pages = result.get("pages")
        if isinstance(pages, list) and pages:
            for p in pages:
                if isinstance(p, dict) and p.get("selected") and isinstance(p.get("id"), int):
                    page_id = p["id"]
                    break
            if page_id is None and isinstance(pages[-1], dict) and isinstance(pages[-1].get("id"), int):
                page_id = pages[-1]["id"]
    if page_id is None:
        try:
            listed = list_pages(sandbox_name)
            if isinstance(listed, dict):
                pages = listed.get("pages")
                if isinstance(pages, list) and pages:
                    for p in pages:
                        if isinstance(p, dict) and p.get("selected") and isinstance(p.get("id"), int):
                            page_id = p["id"]
                            break
                    if page_id is None and isinstance(pages[-1], dict) and isinstance(pages[-1].get("id"), int):
                        page_id = pages[-1]["id"]
        except Exception:
            pass
    return {"url": url, "result": result, "page_id": page_id}


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


def screenshot(sandbox_name: str, page_id: int, *, full_page: bool = False) -> bytes:
    page_id = validate_page_id(page_id)
    path = f"/tmp/mcp-browser-{uuid.uuid4().hex}.jpeg"
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
    metadata_only_js = "true" if metadata_only else "false"
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
      const styleTexts = [...document.querySelectorAll('style')].map(s => s.textContent || '').filter(Boolean);
      return {{
        found: true,
        selector,
        url: location.href,
        title: document.title,
        ...({metadata_only_js}
          ? {{html_bytes: clone.outerHTML.length, css_bytes: styleTexts.join('').length}}
          : {{html: clone.outerHTML, css: styleTexts.join('\\n')}}),
        externalStylesheets: [...document.querySelectorAll('link[rel~="stylesheet"]')].map(link => link.href),
        assets: [...document.querySelectorAll('img[src], source[src], video[src]')].map(node => node.src).filter(Boolean)
      }};
    }}"""
    eval_res = evaluate(sandbox_name, page_id, script)
    res = eval_res.get("result")
    return res if isinstance(res, dict) else {"found": False, "error": str(res)}
