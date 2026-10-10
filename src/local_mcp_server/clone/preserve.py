from __future__ import annotations

import base64
import binascii
import hashlib
import json
import posixpath
import re
import shlex
import uuid
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from ..infrastructure.openshell.sandbox import execute_sandbox_argv
from ..sandbox.policy import validate_name
from .chrome import evaluate, validate_page_id
from .pipeline import (
    _PROJECT_ROOT,
    _safe_relative_project_path,
    create_clone_manifest as create_clone_manifest_impl,
    generate_project as generate_project_impl,
)
from .visual import capture_screenshot_artifact

_MAX_CHUNK_CHARS = 12_000
_MAX_CAPTURE_CHARS = 15_000_000
_MAX_ASSET_COUNT = 50
_MAX_ASSET_BYTES = 2_000_000
_MAX_TOTAL_ASSET_BYTES = 20_000_000
_ASSET_CHUNK_CHARS = 12_000


def _remote_path(relative_path: str) -> str:
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or relative_path.startswith("/")
        or "\\" in relative_path
        or "\x00" in relative_path
        or any(part in {"", ".", ".."} for part in relative_path.split("/"))
    ):
        raise ValueError("Artifact path must be a canonical relative path.")
    if posixpath.normpath(relative_path) != relative_path:
        raise ValueError("Artifact path must be canonical.")
    return f"{_PROJECT_ROOT}/{relative_path}"


def _command(
    sandbox_name: str,
    argv: list[str],
    *,
    stdin: bytes | None = None,
    timeout_seconds: int = 30,
) -> dict[str, object]:
    result = execute_sandbox_argv(
        validate_name(sandbox_name),
        argv,
        stdin=stdin,
        timeout_seconds=timeout_seconds,
    )
    if int(result.get("return_code", 1)) != 0:
        detail = str(result.get("stderr") or result.get("stdout") or "").strip()
        raise RuntimeError(
            f"Sandbox command failed ({argv[0]}): "
            f"{detail[:400] or 'unknown error'}"
        )
    return result


def _create_capture_directory(sandbox_name: str, relative_dir: str) -> str:
    remote_dir = _remote_path(relative_dir)
    parent = posixpath.dirname(remote_dir)
    _command(sandbox_name, ["mkdir", "-p", parent])
    resolved_parent = _command(sandbox_name, ["realpath", "-e", parent])
    if str(resolved_parent.get("stdout", "")).strip() != parent:
        raise ValueError("Capture parent resolves through a symlink.")
    # Deliberately do not use mkdir -p here: a capture ID must never be reused.
    _command(sandbox_name, ["mkdir", remote_dir])
    resolved = _command(sandbox_name, ["realpath", "-e", remote_dir])
    if str(resolved.get("stdout", "")).strip() != remote_dir:
        raise ValueError("Capture directory resolves through a symlink.")
    return remote_dir


def _write_new_file(sandbox_name: str, relative_path: str, content: bytes) -> None:
    remote_path = _remote_path(relative_path)
    parent = posixpath.dirname(remote_path)
    resolved_parent = _command(sandbox_name, ["realpath", "-e", parent])
    if str(resolved_parent.get("stdout", "")).strip() != parent:
        raise ValueError("Artifact parent resolves through a symlink.")

    quoted = shlex.quote(remote_path)
    # Shell noclobber prevents replacing an existing regular file or following a symlink.
    chunk_size = 512 * 1024
    if len(content) <= chunk_size:
        _command(
            sandbox_name,
            ["sh", "-c", f"set -C; cat > {quoted}"],
            stdin=content,
        )
        return

    # For larger payloads exceeding gRPC message size, create first with noclobber then stream remaining
    _command(
        sandbox_name,
        ["sh", "-c", f"set -C; cat > {quoted}"],
        stdin=content[:chunk_size],
    )
    for i in range(chunk_size, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        _command(
            sandbox_name,
            ["sh", "-c", f"cat >> {quoted}"],
            stdin=chunk,
        )


def _evaluate(sandbox_name: str, page_id: int, script: str) -> dict[str, Any]:
    result = evaluate(sandbox_name, page_id, script).get("result")
    if not isinstance(result, dict):
        raise RuntimeError(
            f"Browser evaluation returned an unexpected result: {str(result)[:300]}"
        )
    return result


def _capture_text(
    sandbox_name: str,
    page_id: int,
    kind: str,
) -> tuple[str, dict[str, Any]]:
    if kind not in {"html", "css"}:
        raise ValueError("kind must be 'html' or 'css'.")

    cache_key = "__mcp_raw_capture_" + uuid.uuid4().hex
    key_json = json.dumps(cache_key)
    init_script = f"""() => {{
      const key = {key_json};
      let value = "";
      let meta = {{}};
      if ({json.dumps(kind)} === "html") {{
        value = document.documentElement ? document.documentElement.outerHTML : "";
        meta = {{
          url: location.href,
          title: document.title,
          readyState: document.readyState,
          doctype: document.doctype
            ? new XMLSerializer().serializeToString(document.doctype)
            : null,
          viewport: {{width: innerWidth, height: innerHeight, devicePixelRatio}},
          scroll: {{x: scrollX, y: scrollY}},
          capturedAt: new Date().toISOString()
        }};
      }} else {{
        const blocks = [];
        const inaccessible = [];
        for (const sheet of [...document.styleSheets]) {{
          try {{
            blocks.push("/* stylesheet: " + (sheet.href || "inline") + " */\\n" +
              [...sheet.cssRules].map(rule => rule.cssText).join("\\n"));
          }} catch (error) {{
            inaccessible.push({{href: sheet.href || null, error: String(error)}});
          }}
        }}
        value = blocks.filter(Boolean).join("\\n\\n");
        meta = {{
          stylesheetCount: document.styleSheets.length,
          inaccessibleStylesheets: inaccessible
        }};
      }}
      window[key] = value;
      const end = Math.min(value.length, {_MAX_CHUNK_CHARS});
      const safeEnd = end > 0 && end < value.length &&
        value.charCodeAt(end - 1) >= 0xD800 &&
        value.charCodeAt(end - 1) <= 0xDBFF ? end - 1 : end;
      return {{
        length: value.length,
        chunk: value.slice(0, safeEnd),
        nextOffset: safeEnd,
        meta
      }};
    }}"""
    chunks: list[str] = []
    metadata: dict[str, Any] = {}
    total: int | None = None
    offset = 0

    try:
        first = _evaluate(sandbox_name, page_id, init_script)
        total = first.get("length")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise RuntimeError(f"Browser returned an invalid {kind} length.")
        if total > _MAX_CAPTURE_CHARS:
            raise ValueError(
                f"{kind} capture exceeds the {_MAX_CAPTURE_CHARS}-character limit."
            )
        raw_meta = first.get("meta")
        metadata = raw_meta if isinstance(raw_meta, dict) else {}
        first_chunk = first.get("chunk")
        next_offset = first.get("nextOffset")
        if not isinstance(first_chunk, str) or not isinstance(next_offset, int):
            raise RuntimeError(f"Browser returned an invalid {kind} chunk.")
        chunks.append(first_chunk)
        offset = next_offset

        while offset < total:
            script = f"""() => {{
              const key = {key_json};
              const value = window[key];
              if (typeof value !== "string") return {{error: "snapshot cache missing"}};
              const start = {offset};
              const end = Math.min(value.length, start + {_MAX_CHUNK_CHARS});
              const safeEnd = end > start && end < value.length &&
                value.charCodeAt(end - 1) >= 0xD800 &&
                value.charCodeAt(end - 1) <= 0xDBFF ? end - 1 : end;
              return {{
                length: value.length,
                chunk: value.slice(start, safeEnd),
                nextOffset: safeEnd
              }};
            }}"""
            part = _evaluate(sandbox_name, page_id, script)
            if part.get("length") != total:
                raise RuntimeError(
                    f"{kind} snapshot length changed during chunk retrieval."
                )
            chunk = part.get("chunk")
            next_offset = part.get("nextOffset")
            if not isinstance(chunk, str) or isinstance(next_offset, bool) or not isinstance(next_offset, int):
                raise RuntimeError(f"Browser returned an invalid {kind} chunk.")
            if next_offset <= offset or next_offset > total or not chunk:
                raise RuntimeError(f"Browser returned a non-progressing {kind} chunk.")
            chunks.append(chunk)
            offset = next_offset

        value = "".join(chunks)
        if len(value.encode("utf-16-le", errors="surrogatepass")) // 2 != total:
            raise RuntimeError(f"{kind} snapshot length verification failed.")
        return value, metadata
    finally:
        cleanup = f"() => {{ delete window[{key_json}]; return true; }}"
        try:
            evaluate(sandbox_name, page_id, cleanup)
        except Exception:
            pass


def _capture_inventory(sandbox_name: str, page_id: int) -> dict[str, Any]:
    script = """() => {
      const resourceEntries = performance.getEntriesByType("resource");
      const assetUrls = [...new Set([
        ...[...document.querySelectorAll("img[src]")].map(node => node.currentSrc || node.src),
        ...[...document.querySelectorAll("source[src]")].map(node => node.src),
        ...[...document.querySelectorAll("video[src], audio[src]")].map(node => node.src),
        ...[...document.querySelectorAll('link[rel~="stylesheet"], link[rel~="icon"], link[rel~="preload"], link[rel~="modulepreload"], link[rel="manifest"]')].map(node => node.href),
        ...[...document.querySelectorAll("script[src]")].map(node => node.src),
        ...[...document.querySelectorAll("[poster]")].map(node => node.poster)
      ].filter(Boolean))];
      const links = [...document.querySelectorAll("a[href]")];
      const buttons = [...document.querySelectorAll(
        "button, input[type=button], input[type=submit], [role=button]"
      )];
      const forms = [...document.forms];
      const images = [...document.images];
      const videos = [...document.querySelectorAll("video, source")];
      const fonts = [...document.fonts];
      const stylesheets = [...document.querySelectorAll('link[rel~="stylesheet"]')];
      const scripts = [...document.scripts];

      return {
        url: location.href,
        title: document.title,
        readyState: document.readyState,
        capturedAt: new Date().toISOString(),
        resources: resourceEntries.slice(0, 100).map(entry => ({
          url: entry.name.slice(0, 1024),
          initiatorType: entry.initiatorType || null,
          transferSize: Number.isFinite(entry.transferSize) ? entry.transferSize : null,
          durationMs: Number.isFinite(entry.duration) ? entry.duration : null
        })),
        assets: assetUrls.slice(0, 150).map(url => url.slice(0, 1024)),
        images: images.slice(0, 50).map(node => ({
          src: (node.currentSrc || node.src).slice(0, 1024),
          width: node.naturalWidth,
          height: node.naturalHeight
        })),
        videos: videos.slice(0, 25).map(node => (node.currentSrc || node.src).slice(0, 1024)).filter(Boolean),
        fonts: fonts.slice(0, 100).map(font => String(font.family).slice(0, 200)),
        externalStylesheets: stylesheets.slice(0, 50).map(link => link.href.slice(0, 1024)).filter(Boolean),
        scripts: scripts.slice(0, 50).map(node => node.src.slice(0, 1024)).filter(Boolean),
        interactions: {
          links: links.slice(0, 75).map(node => ({
            text: (node.innerText || node.textContent || "").trim().slice(0, 300),
            href: node.href.slice(0, 1024)
          })),
          buttons: buttons.slice(0, 100).map(node => ({
            text: (node.innerText || node.value || node.getAttribute("aria-label") || "").trim().slice(0, 300),
            tag: node.tagName.toLowerCase(),
            id: (node.id || "").slice(0, 200) || null
          })),
          forms: forms.slice(0, 25).map(form => ({
            action: (form.action || "").slice(0, 1024) || null,
            method: (form.method || "get").toLowerCase()
          }))
        },
        inventory_limits: {
          resources: {observed: resourceEntries.length, captured: Math.min(resourceEntries.length, 100), truncated: resourceEntries.length > 100},
          assets: {observed: assetUrls.length, captured: Math.min(assetUrls.length, 150), truncated: assetUrls.length > 150},
          images: {observed: images.length, captured: Math.min(images.length, 50), truncated: images.length > 50},
          videos: {observed: videos.length, captured: Math.min(videos.length, 25), truncated: videos.length > 25},
          fonts: {observed: fonts.length, captured: Math.min(fonts.length, 100), truncated: fonts.length > 100},
          stylesheets: {observed: stylesheets.length, captured: Math.min(stylesheets.length, 50), truncated: stylesheets.length > 50},
          scripts: {observed: scripts.length, captured: Math.min(scripts.length, 50), truncated: scripts.length > 50},
          links: {observed: links.length, captured: Math.min(links.length, 75), truncated: links.length > 75},
          buttons: {observed: buttons.length, captured: Math.min(buttons.length, 100), truncated: buttons.length > 100},
          forms: {observed: forms.length, captured: Math.min(forms.length, 25), truncated: forms.length > 25}
        }
      };
    }"""
    return _evaluate(sandbox_name, page_id, script)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _remote_sha256(sandbox_name: str, relative_path: str) -> str:
    remote_path = _remote_path(relative_path)
    resolved = _command(sandbox_name, ["realpath", "-e", remote_path])
    if str(resolved.get("stdout", "")).strip() != remote_path:
        raise ValueError("Artifact path resolves through a symlink.")
    result = _command(sandbox_name, ["sha256sum", remote_path])
    digest = str(result.get("stdout", "")).strip().split(maxsplit=1)
    if not digest or not re.fullmatch(r"[0-9a-fA-F]{64}", digest[0]):
        raise RuntimeError(f"Could not verify SHA-256 for {relative_path}.")
    return digest[0].lower()


def _remote_size(sandbox_name: str, relative_path: str) -> int:
    remote_path = _remote_path(relative_path)
    resolved = _command(sandbox_name, ["realpath", "-e", remote_path])
    if str(resolved.get("stdout", "")).strip() != remote_path:
        raise ValueError("Artifact path resolves through a symlink.")
    result = _command(sandbox_name, ["stat", "-c", "%s", remote_path])
    try:
        size = int(str(result.get("stdout", "")).strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not verify byte size for {relative_path}.") from exc
    if size < 0:
        raise RuntimeError(f"Invalid byte size for {relative_path}.")
    return size


def _write_capture_artifact(
    sandbox_name: str,
    relative_path: str,
    content: bytes,
) -> dict[str, Any]:
    _write_new_file(sandbox_name, relative_path, content)
    return {
        "path": relative_path,
        "bytes": len(content),
        "sha256": _remote_sha256(sandbox_name, relative_path),
        "status": "captured",
    }



def _capture_asset_bytes(
    sandbox_name: str,
    page_id: int,
    url: str,
) -> tuple[bytes | None, dict[str, Any]]:
    """Fetch a page-referenced same-origin asset without cookies, then stream base64 chunks."""
    cache_key = "__mcp_raw_asset_" + uuid.uuid4().hex
    key_json = json.dumps(cache_key)
    url_json = json.dumps(url)
    init_script = f"""async () => {{
      const key = {key_json};
      try {{
        const url = new URL({url_json}, location.href);
        if (url.protocol !== "http:" && url.protocol !== "https:") {{
          return {{status: "skipped_unsupported_scheme", url: url.href}};
        }}
        if (url.username || url.password) {{
          return {{status: "skipped_embedded_credentials", url: url.origin}};
        }}
        if (url.origin !== location.origin) {{
          return {{status: "skipped_cross_origin", url: url.href}};
        }}
        const response = await fetch(url.href, {{
          method: "GET",
          mode: "same-origin",
          credentials: "omit",
          redirect: "error",
          cache: "no-store"
        }});
        if (!response.ok) {{
          return {{status: "failed", url: url.href, error: "HTTP " + response.status}};
        }}
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength > {_MAX_ASSET_BYTES}) {{
          return {{
            status: "skipped_asset_size_limit",
            url: url.href,
            bytes: buffer.byteLength,
            contentType: response.headers.get("content-type") || null
          }};
        }}
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 0x8000) {{
          binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
        }}
        const encoded = btoa(binary);
        window[key] = encoded;
        return {{
          status: "ready",
          url: url.href,
          bytes: buffer.byteLength,
          base64Length: encoded.length,
          contentType: response.headers.get("content-type") || null
        }};
      }} catch (error) {{
        return {{status: "failed", url: {url_json}, error: String(error).slice(0, 400)}};
      }}
    }}"""
    try:
        metadata = _evaluate(sandbox_name, page_id, init_script)
        if metadata.get("status") != "ready":
            return None, metadata
        expected_bytes = metadata.get("bytes")
        total_encoded = metadata.get("base64Length")
        if (
            isinstance(expected_bytes, bool)
            or not isinstance(expected_bytes, int)
            or not 0 <= expected_bytes <= _MAX_ASSET_BYTES
            or isinstance(total_encoded, bool)
            or not isinstance(total_encoded, int)
            or total_encoded < 0
        ):
            return None, {"status": "failed", "url": url, "error": "Invalid asset metadata."}

        chunks: list[bytes] = []
        offset = 0
        while offset < total_encoded:
            script = f"""() => {{
              const value = window[{key_json}];
              if (typeof value !== "string") return {{error: "asset cache missing"}};
              const start = {offset};
              const end = Math.min(value.length, start + {_ASSET_CHUNK_CHARS});
              return {{length: value.length, chunk: value.slice(start, end), nextOffset: end}};
            }}"""
            part = _evaluate(sandbox_name, page_id, script)
            chunk = part.get("chunk")
            next_offset = part.get("nextOffset")
            if (
                part.get("length") != total_encoded
                or not isinstance(chunk, str)
                or isinstance(next_offset, bool)
                or not isinstance(next_offset, int)
                or next_offset <= offset
                or next_offset > total_encoded
            ):
                return None, {"status": "failed", "url": url, "error": "Invalid asset chunk."}
            try:
                chunks.append(base64.b64decode(chunk, validate=True))
            except (ValueError, binascii.Error):
                return None, {"status": "failed", "url": url, "error": "Invalid base64 asset chunk."}
            offset = next_offset

        data = b"".join(chunks)
        if len(data) != expected_bytes:
            return None, {"status": "failed", "url": url, "error": "Asset byte count verification failed."}
        return data, metadata
    finally:
        try:
            evaluate(
                sandbox_name,
                page_id,
                f"() => {{ delete window[{key_json}]; return true; }}",
            )
        except Exception:
            pass


def _asset_extension(url: str, content_type: object) -> str:
    mime = str(content_type or "").split(";", 1)[0].strip().lower()
    by_mime = {
        "text/css": ".css",
        "text/javascript": ".js",
        "application/javascript": ".js",
        "application/json": ".json",
        "image/avif": ".avif",
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
        "font/woff": ".woff",
        "font/woff2": ".woff2",
        "application/font-woff": ".woff",
        "application/pdf": ".pdf",
        "video/mp4": ".mp4",
        "audio/mpeg": ".mp3",
    }
    if mime in by_mime:
        return by_mime[mime]
    suffix = posixpath.splitext(urllib.parse.urlsplit(url).path)[1].lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) and suffix not in {".html", ".htm"}:
        return suffix
    return ".bin"


def _capture_assets(
    sandbox_name: str,
    page_id: int,
    capture_dir: str,
    urls: list[str],
    asset_status: list[dict[str, Any]],
    page_url: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
    files: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    total_bytes = 0
    status_by_url = {
        item.get("url"): item for item in asset_status if isinstance(item, dict)
    }
    unique_urls = list(dict.fromkeys(url for url in urls if isinstance(url, str) and url))
    source_origin: str | None = None
    if isinstance(page_url, str):
        parsed_source = urllib.parse.urlsplit(page_url)
        if parsed_source.scheme.lower() in {"http", "https"} and parsed_source.netloc:
            source_origin = f"{parsed_source.scheme.lower()}://{parsed_source.netloc.lower()}"

    for index, url in enumerate(unique_urls):
        status = status_by_url.get(url)
        if status is None:
            status = {"url": url, "status": "inventoried_not_downloaded"}
            asset_status.append(status)
            status_by_url[url] = status
        if source_origin:
            parsed_asset = urllib.parse.urlsplit(url)
            asset_origin = (
                f"{parsed_asset.scheme.lower()}://{parsed_asset.netloc.lower()}"
                if parsed_asset.scheme.lower() in {"http", "https"} and parsed_asset.netloc
                else None
            )
            if asset_origin and asset_origin != source_origin:
                status["status"] = "skipped_cross_origin"
                status["reason"] = "Cross-origin downloads are not attempted by this capture policy."
                continue
        if index >= _MAX_ASSET_COUNT:
            status["status"] = "skipped_asset_count_limit"
            continue
        if total_bytes >= _MAX_TOTAL_ASSET_BYTES:
            status["status"] = "skipped_total_size_limit"
            continue

        try:
            data, metadata = _capture_asset_bytes(sandbox_name, page_id, url)
            asset_state = metadata.get("status", "failed")
            if data is None:
                status["status"] = asset_state
                if asset_state == "failed":
                    error = str(metadata.get("error") or "Asset fetch failed.")
                    status["error"] = error
                    failures.append({
                        "artifact": f"asset:{url[:200]}",
                        "error": error,
                    })
                continue
            if total_bytes + len(data) > _MAX_TOTAL_ASSET_BYTES:
                status["status"] = "skipped_total_size_limit"
                continue

            extension = _asset_extension(url, metadata.get("contentType"))
            relative_path = f"{capture_dir}/assets/asset-{index + 1:03d}{extension}"
            assets_dir = _remote_path(f"{capture_dir}/assets")
            _command(sandbox_name, ["mkdir", "-p", assets_dir])
            resolved_assets_dir = _command(sandbox_name, ["realpath", "-e", assets_dir])
            if str(resolved_assets_dir.get("stdout", "")).strip() != assets_dir:
                raise ValueError("Asset directory resolves through a symlink.")
            file_entry = _write_capture_artifact(sandbox_name, relative_path, data)
            files.append(file_entry)
            total_bytes += len(data)
            status.update({
                "status": "captured",
                "path": relative_path,
                "bytes": len(data),
                "sha256": file_entry["sha256"],
                "content_type": metadata.get("contentType"),
            })
        except Exception as exc:
            status["status"] = "failed"
            status["error"] = f"{type(exc).__name__}: {exc}"
            failures.append({
                "artifact": f"asset:{url[:200]}",
                "error": status["error"],
            })

    return files, failures, total_bytes


def capture_raw_snapshot(
    sandbox_name: str,
    page_id: int,
    *,
    full_page_screenshot: bool = True,
) -> dict[str, Any]:
    """Capture a non-converted browser snapshot into a new immutable directory.

    HTML is the serialized rendered DOM, not the original HTTP response bytes.
    CSS is the CSSOM text accessible to the page. Asset URLs are inventoried,
    and bounded same-origin asset downloads are attempted without sending cookies.
    """
    name = validate_name(sandbox_name)
    page_id = validate_page_id(page_id)
    capture_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%sz")
        + "-" + uuid.uuid4().hex[:12]
    )
    relative_dir = f"captures/{capture_id}"
    _create_capture_directory(name, relative_dir)

    files: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    inventory: dict[str, Any] = {}
    html_meta: dict[str, Any] = {}
    css_meta: dict[str, Any] = {}
    asset_bytes_preserved = 0

    try:
        html_text, html_meta = _capture_text(name, page_id, "html")
        if not html_text:
            raise RuntimeError("Rendered DOM was empty.")
        html_path = f"{relative_dir}/dom.snapshot.html"
        files.append(_write_capture_artifact(name, html_path, html_text.encode("utf-8")))
    except Exception as exc:
        failures.append({"artifact": "dom.snapshot.html", "error": f"{type(exc).__name__}: {exc}"})

    try:
        css_text, css_meta = _capture_text(name, page_id, "css")
        css_path = f"{relative_dir}/stylesheets.snapshot.css"
        files.append(_write_capture_artifact(name, css_path, css_text.encode("utf-8")))
    except Exception as exc:
        failures.append({"artifact": "stylesheets.snapshot.css", "error": f"{type(exc).__name__}: {exc}"})

    try:
        inventory = _capture_inventory(name, page_id)
    except Exception as exc:
        inventory = {
            "url": html_meta.get("url"),
            "title": html_meta.get("title"),
            "resources": [],
            "assets": [],
            "interactions": {"links": [], "buttons": [], "forms": []},
            "inventory_error": f"{type(exc).__name__}: {exc}",
        }
        failures.append({"artifact": "runtime-inventory", "error": inventory["inventory_error"]})

    inventory["html_capture"] = html_meta
    inventory["css_capture"] = css_meta
    resource_urls = [
        item.get("url")
        for item in inventory.get("resources", [])
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    ]
    all_asset_urls = list(dict.fromkeys([
        url for url in [*inventory.get("assets", []), *resource_urls]
        if isinstance(url, str) and url
    ]))
    inventory["asset_status"] = [
        {"url": url, "status": "inventoried_not_downloaded"}
        for url in all_asset_urls
    ]
    try:
        asset_files, asset_failures, asset_bytes_preserved = _capture_assets(
            name,
            page_id,
            relative_dir,
            all_asset_urls,
            inventory["asset_status"],
            inventory.get("url") or html_meta.get("url"),
        )
        files.extend(asset_files)
        failures.extend(asset_failures)
    except Exception as exc:
        asset_error = f"{type(exc).__name__}: {exc}"
        failures.append({"artifact": "assets", "error": asset_error})
        for asset in inventory["asset_status"]:
            if asset.get("status") == "inventoried_not_downloaded":
                asset.update({"status": "failed", "error": asset_error})
    inventory["capture"] = {
        "id": capture_id,
        "page_id": page_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "representation": "serialized-rendered-dom",
        "raw_preservation": True,
        "conversion_performed": False,
        "limitations": [
            "Rendered DOM is not the original HTTP response body.",
            "JavaScript event listeners and private runtime state cannot be serialized completely.",
            "Cross-origin CSS rules may be inaccessible due to browser security restrictions.",
            "Asset bytes are attempted only for same-origin URLs with credentials omitted; inaccessible or skipped resources retain an explicit status.",
        ],
    }
    inventory_path = f"{relative_dir}/capture.json"
    try:
        inventory_bytes = (json.dumps(inventory, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        files.append(_write_capture_artifact(name, inventory_path, inventory_bytes))
    except Exception as exc:
        failures.append({"artifact": "capture.json", "error": f"{type(exc).__name__}: {exc}"})

    screenshot_path = f"{relative_dir}/screenshot.png"
    try:
        screenshot_result = capture_screenshot_artifact(
            name, page_id, screenshot_path, full_page=full_page_screenshot
        )
        files.append({
            "path": screenshot_path,
            "bytes": screenshot_result.get("bytes"),
            "sha256": _remote_sha256(name, screenshot_path),
            "status": "captured",
        })
    except Exception as exc:
        screenshot_result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        failures.append({"artifact": "screenshot.png", "error": screenshot_result["error"]})
        files.append({"path": screenshot_path, "status": "failed", "error": screenshot_result["error"]})

    asset_urls = inventory.get("asset_status", inventory.get("assets", []))
    manifest = {
        "schema_version": "1.0.0",
        "capture_id": capture_id,
        "source": {
            "url": inventory.get("url") or html_meta.get("url"),
            "title": inventory.get("title") or html_meta.get("title"),
            "page_id": page_id,
        },
        "capture": {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "raw_preservation": True,
            "conversion_performed": False,
            "limitations": [
                "Rendered DOM is not the original HTTP response body.",
                "Asset bytes are attempted only for same-origin URLs with credentials omitted; inaccessible or skipped resources retain an explicit status.",
                "Only CSS rules readable through the page CSSOM are preserved.",
            ],
        },
        "files": files,
        "failures": failures,
        "screenshot": screenshot_result,
        "assets": inventory.get("asset_status", []),
        "inventory_limits": inventory.get("inventory_limits", {}),
        "asset_count": len(asset_urls) if isinstance(asset_urls, list) else 0,
        "asset_bytes_preserved": asset_bytes_preserved,
        "integrity": {
            "algorithm": "sha256",
            "manifest_hash": "not_applicable_self_hash",
        },
        "completeness": {
            "has_failures": bool(failures),
            "assets_captured": sum(
                1 for item in inventory.get("asset_status", [])
                if isinstance(item, dict) and item.get("status") == "captured"
            ),
            "assets_not_captured": sum(
                1 for item in inventory.get("asset_status", [])
                if isinstance(item, dict) and item.get("status") != "captured"
            ),
            "inventory_truncated": any(
                isinstance(value, dict) and value.get("truncated") is True
                for value in inventory.get("inventory_limits", {}).values()
            ),
        },
        "status": "partial" if (
            failures
            or any(
                isinstance(item, dict) and item.get("status") != "captured"
                for item in inventory.get("asset_status", [])
            )
            or any(
                isinstance(value, dict) and value.get("truncated") is True
                for value in inventory.get("inventory_limits", {}).values()
            )
        ) else "captured_with_limitations",
    }
    manifest_path = f"{relative_dir}/manifest.json"
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write_new_file(name, manifest_path, manifest_bytes)

    return {
        "status": manifest["status"],
        "capture_id": capture_id,
        "capture_dir": relative_dir,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "conversion_performed": False,
    }



def _read_artifact_text(
    sandbox_name: str,
    relative_path: str,
    *,
    max_bytes: int = 40_000_000,
) -> str:
    remote_path = _remote_path(relative_path)
    resolved = _command(sandbox_name, ["realpath", "-e", remote_path])
    if str(resolved.get("stdout", "")).strip() != remote_path:
        raise ValueError("Raw snapshot file resolves through a symlink.")
    size_result = _command(sandbox_name, ["stat", "-c", "%s", remote_path])
    try:
        size = int(str(size_result.get("stdout", "")).strip())
    except ValueError as exc:
        raise ValueError("Could not determine raw snapshot file size.") from exc
    if size < 0 or size > max_bytes:
        raise ValueError(f"Raw snapshot file exceeds the {max_bytes}-byte limit.")
    result = _command(sandbox_name, ["cat", remote_path], timeout_seconds=60)
    value = result.get("stdout", "")
    if not isinstance(value, str) or len(value.encode("utf-8")) != size:
        raise RuntimeError("Raw snapshot file size changed or could not be decoded.")
    return value


def convert_raw_snapshot(
    sandbox_name: str,
    capture_dir: str,
    output_dir: str = "clones/from-raw-snapshot",
) -> dict[str, Any]:
    """Convert a previously captured raw snapshot without recapturing the website.

    The capture directory is read-only for this operation. Conversion uses the
    existing sanitizer/generator and writes only to a new, separate output path.
    """
    name = validate_name(sandbox_name)
    normalized_capture_dir = _safe_relative_project_path(
        capture_dir, field="capture_dir"
    )
    if normalized_capture_dir != capture_dir:
        raise ValueError("capture_dir must be canonical and contain no dot segments.")
    parts = normalized_capture_dir.split("/")
    if len(parts) != 2 or parts[0] != "captures" or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{0,79}", parts[1]
    ):
        raise ValueError("capture_dir must identify one directory under captures/.")

    normalized_output_dir = _safe_relative_project_path(
        output_dir, field="output_dir"
    )
    if normalized_output_dir == "captures" or normalized_output_dir.startswith("captures/"):
        raise ValueError("output_dir must be separate from the raw captures directory.")
    output_remote = _remote_path(normalized_output_dir)
    exists = execute_sandbox_argv(
        name,
        ["sh", "-c", '[ ! -e "$1" ] && [ ! -L "$1" ]', "sh", output_remote],
        timeout_seconds=10,
    )
    if int(exists.get("return_code", 1)) != 0:
        raise FileExistsError("Conversion output directory already exists; choose a new output_dir.")

    manifest_path = f"{normalized_capture_dir}/manifest.json"
    manifest = json.loads(_read_artifact_text(name, manifest_path))
    if not isinstance(manifest, dict) or manifest.get("capture_id") != parts[1]:
        raise ValueError("Capture manifest does not match capture_dir.")
    if manifest.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported raw snapshot manifest schema.")
    file_entries = manifest.get("files")
    if not isinstance(file_entries, list):
        raise ValueError("Capture manifest has no file inventory.")

    listed_paths: list[str] = []
    for entry in file_entries:
        if not isinstance(entry, dict) or entry.get("status") != "captured":
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path.startswith(normalized_capture_dir + "/"):
            raise ValueError("Manifest contains a file path outside its capture directory.")
        listed_paths.append(path[len(normalized_capture_dir) + 1 :])
    if len(listed_paths) != len(set(listed_paths)):
        raise ValueError("Capture manifest lists a file more than once.")
    actual_listing = _command(
        name,
        ["find", _remote_path(normalized_capture_dir), "-type", "f", "-printf", "%P\\n"],
        timeout_seconds=30,
    )
    actual_paths = {
        line.strip()
        for line in str(actual_listing.get("stdout", "")).splitlines()
        if line.strip()
    }
    expected_paths = set(listed_paths) | {"manifest.json"}
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        unlisted = sorted(actual_paths - expected_paths)
        raise ValueError(
            "Capture directory and manifest file inventory differ. "
            f"Missing files: {missing[:10]}; unlisted files: {unlisted[:10]}."
        )

    captured_files: dict[str, str] = {}
    for entry in file_entries:
        if not isinstance(entry, dict) or entry.get("status") != "captured":
            continue
        path = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(path, str) or not path.startswith(normalized_capture_dir + "/"):
            raise ValueError("Manifest contains a file path outside its capture directory.")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError(f"Manifest has no valid SHA-256 for {path}.")
        actual_hash = _remote_sha256(name, path)
        if actual_hash != expected_hash:
            raise ValueError(f"Raw snapshot integrity check failed for {path}.")
        expected_size = entry.get("bytes")
        if isinstance(expected_size, int) and not isinstance(expected_size, bool):
            actual_size = _remote_size(name, path)
            if actual_size != expected_size:
                raise ValueError(
                    f"Raw snapshot byte-size check failed for {path}: "
                    f"manifest={expected_size}, actual={actual_size}."
                )
        if path.endswith(("/dom.snapshot.html", "/stylesheets.snapshot.css", "/capture.json")):
            captured_files[path.rsplit("/", 1)[-1]] = _read_artifact_text(name, path)

    if "dom.snapshot.html" not in captured_files:
        raise ValueError("Raw snapshot has no successfully captured DOM.")
    if "capture.json" not in captured_files:
        raise ValueError("Raw snapshot has no successfully captured capture.json inventory.")

    inventory = json.loads(captured_files["capture.json"])
    if not isinstance(inventory, dict):
        raise ValueError("Raw snapshot capture.json is invalid.")
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("url"), str):
        raise ValueError("Raw snapshot manifest has no source URL.")
    source_url = source["url"]
    parsed_url = urllib.parse.urlsplit(source_url)
    if parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("Raw snapshot source URL is not a valid HTTP(S) URL.")

    raw_html = captured_files["dom.snapshot.html"]
    raw_css = captured_files.get("stylesheets.snapshot.css", "")
    interactions = inventory.get("interactions")
    if not isinstance(interactions, dict):
        interactions = {"links": [], "buttons": [], "forms": []}
    assets = {
        "images": inventory.get("images", []),
        "videos": inventory.get("videos", []),
        "fonts": inventory.get("fonts", []),
        "stylesheets": inventory.get("externalStylesheets", []),
        "scripts": inventory.get("scripts", []),
        "resources": inventory.get("resources", []),
        "asset_status": inventory.get("asset_status", []),
    }
    evidence = {
        "discover": {
            "url": source_url,
            "page_id": source.get("page_id"),
            "pages": [{"id": source.get("page_id"), "url": source_url, "selected": True}],
        },
        "inspect_runtime": {
            "url": source_url,
            "title": source.get("title") or inventory.get("title") or "",
            "readyState": inventory.get("readyState"),
        },
        "inspect_page": {
            "url": source_url,
            "title": source.get("title") or inventory.get("title") or "",
            "html": raw_html,
            "css": raw_css,
            "externalStylesheets": assets["stylesheets"],
        },
        "trace_assets": assets,
        "trace_interactions": interactions,
    }
    clone_manifest = create_clone_manifest_impl(**evidence)
    generated = generate_project_impl(
        name,
        normalized_output_dir,
        clone_manifest,
    )
    return {
        "status": "converted",
        "capture_dir": normalized_capture_dir,
        "output_dir": normalized_output_dir,
        "manifest_path": manifest_path,
        "integrity_verified": True,
        "conversion_performed": True,
        "generated": generated,
    }
