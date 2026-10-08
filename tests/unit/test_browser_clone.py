from __future__ import annotations

import pytest

from local_mcp_server.browser import service as browser_service
from local_mcp_server.clone import service as clone_service


def test_validate_url_accepts_public_http_and_https():
    assert browser_service.validate_url("https://example.com/path?q=1") == "https://example.com/path?q=1"
    assert browser_service.validate_url("http://example.com") == "http://example.com"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com",
        "javascript:alert(1)",
        "https://user:pass@example.com",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.10",
        "http://224.0.0.1",
    ],
)
def test_validate_url_rejects_unsafe_targets(url: str):
    with pytest.raises(browser_service.BrowserError):
        browser_service.validate_url(url)


def test_validate_url_rejects_oversized_url():
    with pytest.raises(browser_service.BrowserError, match="2048"):
        browser_service.validate_url("https://example.com/" + "a" * 2048)


@pytest.mark.parametrize("page_id", [0, 1, 999])
def test_validate_page_id_accepts_non_negative_integers(page_id: int):
    assert browser_service.validate_page_id(page_id) == page_id


@pytest.mark.parametrize("page_id", [-1, True, False, "1", 1.0])
def test_validate_page_id_rejects_invalid_values(page_id):
    with pytest.raises(browser_service.BrowserError):
        browser_service.validate_page_id(page_id)


def test_validate_selector_trims_and_limits():
    assert browser_service.validate_selector("  main.hero  ") == "main.hero"
    with pytest.raises(browser_service.BrowserError):
        browser_service.validate_selector("")


def test_validate_selector_rejects_oversized_value():
    with pytest.raises(browser_service.BrowserError, match="2048"):
        browser_service.validate_selector("a" * 2049)


def test_evaluate_rejects_empty_and_oversized_scripts(monkeypatch):
    with pytest.raises(browser_service.BrowserError):
        browser_service.evaluate("sandbox", 1, " ")

    with pytest.raises(browser_service.BrowserError, match="16384"):
        browser_service.evaluate("sandbox", 1, "x" * 16385)


def test_parse_cli_output_accepts_plain_json():
    assert browser_service._parse_cli_output({"return_code": 0, "stdout": '{"pages":[{"id":1}]}'}) == {
        "pages": [{"id": 1}]
    }


def test_parse_cli_output_unwraps_mcp_text_envelope():
    result = browser_service._parse_cli_output(
        {"return_code": 0, "stdout": r'[{"type":"text","text":"{\"id\":7}"}]'}
    )
    assert result == {"id": 7}


def test_parse_cli_output_returns_plain_text():
    assert browser_service._parse_cli_output({"return_code": 0, "stdout": "ok"}) == "ok"


def test_parse_cli_output_raises_on_command_failure():
    with pytest.raises(browser_service.BrowserError, match="boom"):
        browser_service._parse_cli_output(
            {"return_code": 1, "stderr": "boom", "stdout": ""}
        )


def test_run_validates_sandbox_and_adds_json_output(monkeypatch):
    captured = {}

    def fake_execute(**kwargs):
        captured.update(kwargs)
        return {"return_code": 0, "stdout": '{"ok":true}'}

    monkeypatch.setattr(browser_service, "execute_chrome_devtools", fake_execute)
    assert browser_service._run("sandbox-1", "list_pages") == {"ok": True}
    assert captured["sandbox_name"] == "sandbox-1"
    assert "--output-format=json" in captured["arguments"]


def test_screenshot_cleans_up_temp_file(monkeypatch):
    calls = []

    monkeypatch.setattr(
        browser_service,
        "_run",
        lambda *args, **kwargs: calls.append(("devtools", args, kwargs)) or {},
    )

    def fake_argv(sandbox, argv, timeout_seconds):
        calls.append(("argv", sandbox, argv))
        if argv[0] == "base64":
            return {"return_code": 0, "stdout": "aGVsbG8="}
        return {"return_code": 0, "stdout": ""}

    monkeypatch.setattr(browser_service, "execute_sandbox_argv", fake_argv)

    assert browser_service.screenshot("sandbox-1", 2) == b"hello"
    assert any(c[0] == "argv" and c[2][:2] == ["rm", "-f"] for c in calls)


def test_sanitize_html_removes_executable_content_and_dangerous_urls():
    html = '''
    <div onclick="alert(1)">
      <script>alert(2)</script>
      <iframe src="https://evil.example"></iframe>
      <meta http-equiv="refresh" content="0;url=https://evil.example">
      <a href="javascript:alert(3)">bad</a>
      <img src="vbscript:evil">
      <form action="data:text/html,<script>alert(4)</script>"></form>
    </div>
    '''
    sanitized = clone_service._sanitize_html(html)
    assert "<script" not in sanitized.lower()
    assert "<iframe" not in sanitized.lower()
    assert "onclick=" not in sanitized.lower()
    assert "http-equiv=" not in sanitized.lower()
    assert "javascript:" not in sanitized.lower()
    assert "vbscript:" not in sanitized.lower()
    assert "data:text/html" not in sanitized.lower()


def test_sanitize_html_preserves_safe_markup():
    html = '<section id="hero"><h1>Hello</h1><a href="/docs">Docs</a></section>'
    assert clone_service._sanitize_html(html) == html


def test_sanitize_css_limits_size_and_escapes_style_breakout():
    css = "a{color:red}</STYLE><script>alert(1)</script>" + ("x" * 1_000_100)
    sanitized = clone_service._sanitize_css(css)
    assert "</style" not in sanitized.lower()
    assert len(sanitized.encode("utf-8")) <= 1_000_000


def test_safe_slug_produces_filesystem_safe_names():
    assert clone_service._safe_slug("  My / Landing: Page!  ") == "My-Landing-Page"
    assert clone_service._safe_slug("...") == "..."


def test_clone_preview_returns_metadata_without_writing(monkeypatch):
    payload = {
        "found": True,
        "url": "https://example.com/",
        "title": "Example",
        "html": "<main>Hello</main>",
        "css": "main{display:block}",
        "externalStylesheets": ["https://example.com/site.css"],
        "assets": ["https://example.com/hero.png"],
    }
    monkeypatch.setattr(clone_service, "extract_clone_payload", lambda *args, **kwargs: payload)

    result = clone_service.clone_preview("sandbox-1", 1, "main")
    assert result["kind"] == "region"
    assert result["source_url"] == "https://example.com/"
    assert result["selector"] == "main"
    assert result["html_bytes"] == len(payload["html"].encode())
    assert result["css_bytes"] == len(payload["css"].encode())
    assert result["external_stylesheets"] == payload["externalStylesheets"]


def test_clone_preview_rejects_missing_selector(monkeypatch):
    monkeypatch.setattr(
        clone_service,
        "extract_clone_payload",
        lambda *args, **kwargs: {"found": False, "selector": ".missing"},
    )
    with pytest.raises(browser_service.BrowserError, match="did not match"):
        clone_service.clone_preview("sandbox-1", 1, ".missing")


def test_clone_region_writes_sanitized_index(monkeypatch):
    payload = {
        "found": True,
        "url": "https://example.com/",
        "title": "Demo Page",
        "html": '<main onclick="x"><script>x</script><h1>Hello</h1></main>',
        "css": "main{color:red}</style>",
        "externalStylesheets": [],
        "assets": [],
    }
    writes = []
    dirs = []
    monkeypatch.setattr(clone_service, "extract_clone_payload", lambda *args: payload)
    monkeypatch.setattr(clone_service, "create_sandbox_workspace_directory", lambda *args: dirs.append(args))
    monkeypatch.setattr(clone_service, "write_sandbox_file", lambda *args: writes.append(args))

    result = clone_service.clone_region("sandbox-1", 1, "main")
    assert result["output"] == "clones/Demo-Page-region/index.html"
    assert dirs
    assert writes
    document = writes[0][2]
    assert "<script" not in document.lower()
    assert "onclick=" not in document.lower()
    assert "</style><script" not in document.lower()


def test_clone_page_escapes_title_and_writes_output(monkeypatch):
    payload = {
        "found": True,
        "url": "https://example.com/",
        "title": '<img src=x onerror="alert(1)">',
        "html": "<main>Hello</main>",
        "css": "main{color:red}",
        "externalStylesheets": [],
        "assets": [],
    }
    writes = []
    monkeypatch.setattr(clone_service, "extract_clone_payload", lambda *args: payload)
    monkeypatch.setattr(clone_service, "create_sandbox_workspace_directory", lambda *args: None)
    monkeypatch.setattr(clone_service, "write_sandbox_file", lambda *args: writes.append(args))

    result = clone_service.clone_page("sandbox-1", 1)
    assert result["kind"] == "page"
    document = writes[0][2]
    assert "&lt;img" in document
    title = document.split("<title>", 1)[1].split("</title>", 1)[0]
    assert "<img" not in title
