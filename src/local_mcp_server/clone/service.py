from __future__ import annotations

import re
from html import escape

from ..browser.service import BrowserError, extract_clone_payload, validate_page_id, validate_selector
from ..infrastructure.openshell.sandbox_files import (
    create_sandbox_workspace_directory,
    write_sandbox_file,
)
from ..sandbox.policy import validate_name

_MAX_OUTPUT_BYTES = 1_000_000
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_css(css: str) -> str:
    if not isinstance(css, str):
        return ""
    sanitized = re.sub(r"</style", "<\\/style", css, flags=re.IGNORECASE)
    encoded = sanitized.encode("utf-8")
    if len(encoded) > _MAX_OUTPUT_BYTES:
        sanitized = encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")
    return sanitized


def _sanitize_html(html: str) -> str:
    if not isinstance(html, str):
        raise BrowserError("Browser returned invalid HTML.")
    if len(html.encode("utf-8")) > _MAX_OUTPUT_BYTES:
        raise BrowserError("Clone HTML exceeds the maximum allowed size.")
    # The browser-side extraction already removes executable elements and inline
    # event handlers. Keep a second server-side guard for defense in depth.
    html = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<iframe\b[^>]*>.*?</iframe\s*>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"""\s(on[a-z]+|srcdoc)\s*=\s*(["']).*?\2""", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"""<meta\b[^>]*http-equiv\s*=\s*["']?refresh[^>]*>""", "", html, flags=re.IGNORECASE)
    html = re.sub(
        r"""(\s(?:href|src|action|formaction)\s*=\s*["'])(?:javascript:|vbscript:|data:text/html)[^"']*(["'])""",
        r"\1#\2",
        html,
        flags=re.IGNORECASE,
    )
    return html


def _safe_slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return value[:80] or "clone"


def clone_preview(
    sandbox_name: str,
    page_id: int,
    selector: str | None = None,
) -> dict[str, object]:
    """Inspect what would be cloned without writing files."""
    sandbox_name = validate_name(sandbox_name)
    page_id = validate_page_id(page_id)
    if selector is not None:
        selector = validate_selector(selector)

    payload = extract_clone_payload(
        sandbox_name, page_id, selector, metadata_only=True
    )
    if not isinstance(payload, dict) or not payload.get("found"):
        raise BrowserError(
            f"Selector did not match an element: {selector}"
            if selector
            else "Unable to extract the current page."
        )

    html = str(payload.get("html", ""))
    css = str(payload.get("css", ""))
    return {
        "kind": "region" if selector else "page",
        "source_url": payload.get("url"),
        "title": payload.get("title"),
        "selector": selector,
        "html_bytes": int(payload.get("html_bytes") or len(html.encode("utf-8"))),
        "css_bytes": int(payload.get("css_bytes") or len(css.encode("utf-8"))),
        "external_stylesheets": payload.get("externalStylesheets", []),
        "assets": payload.get("assets", []),
        "will_remove": ["script", "noscript", "iframe", "object", "embed", "inline event handlers"],
    }


def clone_region(
    sandbox_name: str,
    page_id: int,
    selector: str,
    output_dir: str = "clones",
) -> dict[str, object]:
    sandbox_name = validate_name(sandbox_name)
    page_id = validate_page_id(page_id)
    selector = validate_selector(selector)
    payload = extract_clone_payload(sandbox_name, page_id, selector)

    if not isinstance(payload, dict) or not payload.get("found"):
        raise BrowserError(f"Selector did not match an element: {selector}")

    html = _sanitize_html(str(payload.get("html", "")))
    css = _sanitize_css(str(payload.get("css", "")))
    slug = _safe_slug(str(payload.get("title") or "region"))
    relative_dir = f"{output_dir}/{slug}-region"
    create_sandbox_workspace_directory(sandbox_name, relative_dir)
    write_sandbox_file(
        sandbox_name,
        f"{relative_dir}/index.html",
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cloned Region</title>
<style>{css}</style>
<style>body{{margin:0}}img{{max-width:100%}}</style>
</head>
<body>{html}</body>
</html>
""",
    )

    return {
        "kind": "region",
        "source_url": payload.get("url"),
        "selector": selector,
        "output": f"{relative_dir}/index.html",
        "external_stylesheets": payload.get("externalStylesheets", []),
        "assets": payload.get("assets", []),
    }


def clone_page(
    sandbox_name: str,
    page_id: int,
    output_dir: str = "clones",
) -> dict[str, object]:
    sandbox_name = validate_name(sandbox_name)
    page_id = validate_page_id(page_id)
    payload = extract_clone_payload(sandbox_name, page_id)

    if not isinstance(payload, dict) or not payload.get("found"):
        raise BrowserError("Unable to extract the current page.")

    html = _sanitize_html(str(payload.get("html", "")))
    css = _sanitize_css(str(payload.get("css", "")))
    slug = _safe_slug(str(payload.get("title") or "page"))
    relative_dir = f"{output_dir}/{slug}"
    create_sandbox_workspace_directory(sandbox_name, relative_dir)
    write_sandbox_file(
        sandbox_name,
        f"{relative_dir}/index.html",
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(str(payload.get("title") or "Cloned Page"))}</title>
<style>{css}</style>
<style>img{{max-width:100%}}</style>
</head>
<body>{html}</body>
</html>
""",
    )

    return {
        "kind": "page",
        "source_url": payload.get("url"),
        "output": f"{relative_dir}/index.html",
        "external_stylesheets": payload.get("externalStylesheets", []),
        "assets": payload.get("assets", []),
        "note": "V1 creates a static sanitized clone; external stylesheets and assets are reported but not downloaded yet.",
    }
