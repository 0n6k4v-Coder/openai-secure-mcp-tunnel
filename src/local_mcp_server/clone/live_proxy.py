from __future__ import annotations

import posixpath
import re
import shlex
import urllib.parse
import uuid
from typing import Any

from ..infrastructure.openshell.sandbox import execute_sandbox_argv
from ..sandbox.policy import validate_name
from .chrome import evaluate, validate_page_id
from .pipeline import _PROJECT_ROOT, format_text_in_sandbox

# Universal Runtime Shim injected into cloned HTML before </body>
_UNIVERSAL_RUNTIME_SHIM = """<script>
// Universal Snapshot Runtime Shim
(function() {
  function initUniversalSnapshot() {
    // 1. Universal Cookie / Dialog Dismissal Handler (Capture Phase)
    function setupDismissableBanners() {
      const STORAGE_KEY = 'snapshot_cookie_consent';
      const isDismissed = localStorage.getItem(STORAGE_KEY);
      const dialogs = document.querySelectorAll('[role="dialog"], [class*="cookie"], [class*="consent"]');
      if (isDismissed === 'accepted' || isDismissed === 'declined') {
        dialogs.forEach(d => d.remove());
        return;
      }
      document.addEventListener('click', function(e) {
        const btn = e.target.closest('button');
        if (!btn) return;
        const dialog = btn.closest('[role="dialog"], [class*="cookie"], [class*="consent"]');
        if (dialog) {
          e.preventDefault();
          e.stopPropagation();
          const text = (btn.textContent || '').trim();
          const choice = text.includes('ยอมรับ') || text.toLowerCase().includes('accept') ? 'accepted' : 'declined';
          try { localStorage.setItem(STORAGE_KEY, choice); } catch (_) {}
          dialog.remove();
        }
      }, true);
    }

    // 2. Astro / React Island Rehydration Bridge
    function rehydrateIslands() {
      const islands = document.querySelectorAll('astro-island');
      islands.forEach(async (island) => {
        const compExport = island.getAttribute('component-export') || '';

        // Reset entrance animations to frame 0
        if (compExport === 'FadeUp' || compExport === 'SlideIn') {
          const directDiv = island.firstElementChild;
          if (directDiv && directDiv.tagName === 'DIV') {
            directDiv.style.opacity = '0';
            directDiv.style.transform = 'translateY(20px)';
          }
        }

        // React hydrator requires 'ssr' attribute
        if (!island.hasAttribute('ssr')) {
          island.setAttribute('ssr', '');
        }

        if (typeof island.hydrate === 'function') {
          try {
            await island.hydrate();
          } catch (err) {
            console.warn('[SnapshotHydrator] Failed to rehydrate:', compExport, err);
          }
        }
      });
    }

    setupDismissableBanners();
    setTimeout(rehydrateIslands, 60);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(initUniversalSnapshot, 50));
  } else {
    setTimeout(initUniversalSnapshot, 50);
  }
})();
</script>"""


def _normalize_relative_path(path: str) -> str:
    if (
        not isinstance(path, str)
        or not path
        or path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("Target directory must be a canonical relative path.")
    normalized = posixpath.normpath(path)
    if normalized != path:
        raise ValueError("Target directory must be canonical.")
    return normalized


def _write_sandbox_file(
    sandbox_name: str,
    remote_path: str,
    data: bytes | str,
    chunk_size: int = 512 * 1024,
) -> None:
    """Write data to sandbox path, streaming in chunks if data exceeds gRPC size limit."""
    data_bytes = data.encode("utf-8") if isinstance(data, str) else data
    quoted_path = shlex.quote(remote_path)
    if not data_bytes:
        execute_sandbox_argv(sandbox_name, ["sh", "-c", f": > {quoted_path}"])
        return

    if len(data_bytes) <= chunk_size:
        execute_sandbox_argv(
            sandbox_name,
            ["sh", "-c", f"cat > {quoted_path}"],
            stdin=data_bytes,
        )
        return

    tmp_path = f"{remote_path}.tmp.{uuid.uuid4().hex[:8]}"
    quoted_tmp = shlex.quote(tmp_path)
    for i in range(0, len(data_bytes), chunk_size):
        chunk = data_bytes[i : i + chunk_size]
        redir = ">" if i == 0 else ">>"
        res = execute_sandbox_argv(
            sandbox_name,
            ["sh", "-c", f"cat {redir} {quoted_tmp}"],
            stdin=chunk,
        )
        if int(res.get("return_code", 1)) != 0:
            execute_sandbox_argv(sandbox_name, ["rm", "-f", quoted_tmp])
            raise RuntimeError(f"Failed to write file chunk to sandbox: {res.get('stderr')}")
    execute_sandbox_argv(sandbox_name, ["mv", "-f", quoted_tmp, quoted_path])


def create_live_proxy_snapshot(
    sandbox_name: str,
    page_id: int,
    output_dir: str,
    *,
    prepare_scroll: bool = True,
    warmup_wait_ms: int = 1500,
    download_module_chunks: bool = True,
    max_chunk_downloads: int = 40,
    max_image_downloads: int = 150,
) -> dict[str, Any]:
    """Capture a high-fidelity Fast Live-Proxy Snapshot from an active browser page.

    Steps:
    1. Pre-capture preparation: Auto-scroll to trigger IntersectionObservers & wait for network idle.
    2. Extraction: Extract hydrated DOM, CSS, script module URLs, and API endpoints.
    3. Post-processing: Rewrite relative asset URLs (images/videos/fonts) to the origin URL,
       reconcile hidden visibility styles (e.g., opacity: 0 on major sections).
    4. Module preservation: Download client ES module chunks locally to bypass CORS.
    5. Injection: Inject universal snapshot runtime shim for animation rehydration & dialog dismissal.
    """
    name = validate_name(sandbox_name)
    pid = validate_page_id(page_id)
    norm_output = _normalize_relative_path(output_dir)
    remote_output = f"{_PROJECT_ROOT}/{norm_output}"

    # 1. Pre-capture Preparation
    if prepare_scroll:
        scroll_script = f"""async () => {{
          const totalHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
          const viewport = window.innerHeight || 800;
          for (let y = 0; y < totalHeight; y += viewport) {{
            window.scrollTo(0, y);
            await new Promise(r => setTimeout(r, 60));
          }}
          window.scrollTo(0, 0);
          try {{
            const stepBtns = Array.from(document.querySelectorAll('#get-started button, [data-step="1"], [aria-label*="step 1"]'));
            const first = stepBtns.find(b => (b.textContent || '').trim().startsWith('1') || b.getAttribute('aria-label') === '1') || stepBtns[0];
            if (first) first.click();
          }} catch (_) {{}}
          await new Promise(r => setTimeout(r, {warmup_wait_ms}));
          return {{ totalHeight, scrolled: true }};
        }}"""
        evaluate(name, pid, scroll_script)

    # 2. Extract Hydrated DOM and Page Metadata
    extraction_script = """() => {
      const html = document.documentElement.outerHTML;
      const title = document.title;
      const origin = window.location.origin;
      const url = window.location.href;
      
      // Collect all scripts and stylesheets from DOM and performance resource timing
      const perfResources = performance.getEntriesByType('resource');
      const perfScripts = perfResources
        .map(r => r.name)
        .filter(n => n.includes('/_astro/') || n.includes('/_next/') || n.includes('/chunks/') || n.includes('/assets/'))
        .map(n => {
          try { return new URL(n).pathname + new URL(n).search; } catch(_) { return n; }
        });

      const moduleScripts = Array.from(document.querySelectorAll('script[type="module"], script[src]'))
        .map(s => s.getAttribute('src'))
        .filter(src => src && (src.startsWith('/_astro/') || src.startsWith('/_next/') || src.startsWith('/assets/')));
      
      const islandUrls = Array.from(document.querySelectorAll('astro-island[component-url], astro-island[renderer-url]'))
        .flatMap(i => [i.getAttribute('component-url'), i.getAttribute('renderer-url')])
        .filter(Boolean);

      const styleLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"][href]'))
        .map(l => l.getAttribute('href'))
        .filter(href => href && (href.startsWith('/_astro/') || href.startsWith('/_next/') || href.startsWith('/assets/')));

      const allScriptUrls = Array.from(new Set([...moduleScripts, ...islandUrls, ...perfScripts, ...styleLinks]));

      // Unified Asset Discovery: Collect all image, icon, illustration, and media URLs
      const perfMedia = perfResources
        .map(r => r.name)
        .filter(n => /\\.(png|jpg|jpeg|webp|avif|svg|gif|ico)(\\?.*)?$/i.test(n))
        .map(n => {
          try { return new URL(n).pathname; } catch(_) { return n; }
        })
        .filter(p => typeof p === 'string' && p.startsWith('/') && !p.startsWith('//'));

      const domImgs = Array.from(document.querySelectorAll('img[src], link[rel*="icon"], video[poster], source[src]'))
        .flatMap(el => [el.getAttribute('src'), el.getAttribute('href'), el.getAttribute('poster')])
        .filter(Boolean)
        .map(src => {
          try { return src.startsWith('http') ? new URL(src).pathname : src; } catch(_) { return src; }
        })
        .filter(p => typeof p === 'string' && p.startsWith('/') && !p.startsWith('//') && (p.startsWith('/images/') || p.startsWith('/illustrations/') || p.startsWith('/videos/') || p.startsWith('/icons/') || p.startsWith('/favicon')));

      const allMediaUrls = Array.from(new Set([...domImgs, ...perfMedia]));

      // Collect in-page API calls or known data endpoints from performance
      const apiRequests = perfResources
        .map(r => r.name)
        .filter(n => n.includes('/api/'));

      return {
        html,
        title,
        origin,
        url,
        scriptUrls: allScriptUrls,
        imgUrls: allMediaUrls,
        apiRequests: Array.from(new Set(apiRequests))
      };
    }"""
    res = evaluate(name, pid, extraction_script)
    data = res.get("result")
    if not isinstance(data, dict) or "html" not in data:
        raise RuntimeError("Failed to extract hydrated DOM from browser page.")

    raw_html: str = data["html"]
    origin: str = data.get("origin", "")
    script_urls: list[str] = data.get("scriptUrls", [])
    img_urls: list[str] = data.get("imgUrls", [])
    api_requests: list[str] = data.get("apiRequests", [])

    # 3. Post-Processing & Path Normalization
    processed_html = raw_html

    # Ensure CSP meta tag does not block local serving or external assets
    processed_html = re.sub(
        r'<meta\s+http-equiv=["\']Content-Security-Policy["\'][^>]*>',
        "",
        processed_html,
        flags=re.IGNORECASE,
    )

    # Reconcile visibility on key sections (e.g. style="opacity: 0" -> style="opacity: 1")
    def _fix_section_visibility(match: re.Match[str]) -> str:
        tag = match.group(0)
        # replace opacity: 0 with opacity: 1
        tag = re.sub(r'opacity:\s*0(?![.\d])', 'opacity: 1', tag)
        return tag

    processed_html = re.sub(
        r'<(?:section|div|main)[^>]+(?:id=["\'](?:pricing|features|benefits|package)["\']|class=["\'][^"\']*(?:pricing|package)[^"\']*)[^>]*>',
        _fix_section_visibility,
        processed_html,
        flags=re.IGNORECASE,
    )

    # Rewrite relative media URLs to Origin
    if origin:
        for prefix in ["/images/", "/videos/", "/fonts/", "/illustrations/"]:
            processed_html = processed_html.replace(
                f'src="{prefix}', f'src="{origin}{prefix}'
            ).replace(
                f"src='{prefix}", f"src='{origin}{prefix}"
            ).replace(
                f'href="{prefix}', f'href="{origin}{prefix}'
            ).replace(
                f"href='{prefix}", f"href='{origin}{prefix}"
            )

    # Inject Universal Runtime Shim before </body>
    if "</body>" in processed_html:
        processed_html = processed_html.replace("</body>", f"{_UNIVERSAL_RUNTIME_SHIM}\n</body>")
    else:
        processed_html += f"\n{_UNIVERSAL_RUNTIME_SHIM}"

    # 4. Create Directories in Sandbox
    execute_sandbox_argv(name, ["mkdir", "-p", remote_output])

    # Store upstream origin for server-side fallback proxying
    if origin:
        _write_sandbox_file(name, f"{remote_output}/.origin", origin.strip().encode("utf-8"))

    # Write index.html
    formatted_html, _ = format_text_in_sandbox(name, f"{norm_output}/index.html", processed_html)
    _write_sandbox_file(name, f"{remote_output}/index.html", formatted_html.encode("utf-8"))

    # 5. Download Client Module Chunks (to bypass CORS on local ES Module imports)
    downloaded_chunks: list[str] = []
    failed_chunks: list[str] = []
    if download_module_chunks and script_urls:
        for script_rel in script_urls[:max_chunk_downloads]:
            clean_path = script_rel.split("?")[0]
            clean_rel = clean_path.lstrip("/")
            full_script_url = urllib.parse.urljoin(origin + "/", clean_rel)
            local_target = f"{remote_output}/{clean_rel}"
            local_parent = posixpath.dirname(local_target)
            
            # create parent directory
            execute_sandbox_argv(name, ["mkdir", "-p", local_parent])
            
            # fetch via curl
            curl_res = execute_sandbox_argv(
                name,
                ["curl", "-s", "-f", "-o", local_target, full_script_url],
                timeout_seconds=10,
            )
            if curl_res.get("return_code") == 0:
                downloaded_chunks.append(clean_rel)
            else:
                failed_chunks.append(clean_rel)

    # 5b. Download Key Image Assets (Manifest-Driven Batch Downloader)
    downloaded_images: list[str] = []
    if origin and img_urls:
        target_images = list(set(img_urls))
        if max_image_downloads is not None:
            target_images = target_images[:max_image_downloads]
        for img_rel in target_images:
            clean_rel = img_rel.split("?")[0].lstrip("/")
            full_img_url = urllib.parse.urljoin(origin + "/", clean_rel)
            local_img_target = f"{remote_output}/{clean_rel}"
            execute_sandbox_argv(name, ["mkdir", "-p", posixpath.dirname(local_img_target)])
            curl_img = execute_sandbox_argv(
                name,
                ["curl", "-s", "-f", "-o", local_img_target, full_img_url],
                timeout_seconds=5,
            )
            if curl_img.get("return_code") == 0:
                downloaded_images.append(clean_rel)

    # 6. Auto-mock collected API endpoints
    mocked_apis: list[str] = []
    if api_requests and origin:
        for api_url in api_requests:
            parsed = urllib.parse.urlsplit(api_url)
            api_path = parsed.path.lstrip("/")
            if not api_path.startswith("api/"):
                continue
            local_api_target = f"{remote_output}/{api_path}"
            execute_sandbox_argv(name, ["mkdir", "-p", posixpath.dirname(local_api_target)])
            curl_api = execute_sandbox_argv(
                name,
                ["curl", "-s", "-f", "-o", local_api_target, api_url],
                timeout_seconds=5,
            )
            if curl_api.get("return_code") == 0:
                mocked_apis.append(api_path)
                # also write .json variant if not present
                if not api_path.endswith(".json"):
                    execute_sandbox_argv(name, ["cp", local_api_target, f"{local_api_target}.json"])

    return {
        "status": "completed",
        "sandbox_name": name,
        "page_id": pid,
        "output_dir": norm_output,
        "title": data.get("title", ""),
        "origin": origin,
        "downloaded_chunks_count": len(downloaded_chunks),
        "downloaded_chunks": downloaded_chunks,
        "downloaded_images_count": len(downloaded_images),
        "downloaded_images": downloaded_images,
        "failed_chunks": failed_chunks,
        "mocked_apis": mocked_apis,
        "runtime_shim_injected": True,
    }
