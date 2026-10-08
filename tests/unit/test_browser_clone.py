from __future__ import annotations

import pytest

from local_mcp_server.browser import service as browser_service
from local_mcp_server.clone import service as clone_service


@pytest.fixture(autouse=True)
def clear_cdp_relay_state():
    browser_service._CDP_INPUT_READY.clear()
    browser_service._CDP_INPUT_SOCKET_READY.clear()
    yield
    browser_service._CDP_INPUT_READY.clear()
    browser_service._CDP_INPUT_SOCKET_READY.clear()


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


def test_validate_input_text_limits():
    assert browser_service._validate_input_text("hello") == "hello"
    with pytest.raises(browser_service.BrowserError):
        browser_service._validate_input_text("")
    with pytest.raises(browser_service.BrowserError, match="65536"):
        browser_service._validate_input_text("x" * 65537)


@pytest.mark.parametrize("value", [-1, True, "1", None])
def test_validate_coordinate_rejects_invalid_values(value):
    with pytest.raises(browser_service.BrowserError):
        browser_service._validate_coordinate(value, "x")


def test_validate_coordinate_accepts_viewport_values():
    assert browser_service._validate_coordinate(0, "x") == 0
    assert browser_service._validate_coordinate(1280, "x") == 1280


def test_viewport_paths_are_page_scoped():
    paths = browser_service._viewport_paths(7)
    assert paths[0].endswith("screencast-7.jpg")
    assert paths[1].endswith("screencast-7.json")
    assert paths[2].endswith("screencast-7.pid")
    assert paths[3].endswith("screencast-7.log")


def test_viewport_start_validates_dimensions_and_quality():
    with pytest.raises(browser_service.BrowserError):
        browser_service.viewport_start("sandbox-1", 1, width=100)
    with pytest.raises(browser_service.BrowserError):
        browser_service.viewport_start("sandbox-1", 1, height=100)
    with pytest.raises(browser_service.BrowserError):
        browser_service.viewport_start("sandbox-1", 1, quality=10)


def test_viewport_start_launches_persistent_cdp_relay(monkeypatch):
    calls = []

    def fake_argv(sandbox, argv, timeout_seconds):
        calls.append((sandbox, argv, timeout_seconds))
        return {"return_code": 0, "stdout": "1234\n", "stderr": ""}

    monkeypatch.setattr(browser_service, "execute_sandbox_argv", fake_argv)
    result = browser_service.viewport_start("sandbox-1", 3)

    assert result["state"] == "starting"
    joined = "\n".join(" ".join(c[1]) for c in calls)
    assert "mcp-browser-screencast-relay.js" in joined
    assert "mcp-browser-input-3.sock" in joined
    assert "Page.startScreencast" in browser_service._CDP_RELAY_SCRIPT
    assert "everyNthFrame: 4" in browser_service._CDP_RELAY_SCRIPT
    assert "maxFramesInFlight: 1" in browser_service._CDP_RELAY_SCRIPT
    assert "net.createServer" in browser_service._CDP_RELAY_SCRIPT
    assert "inputSocketPath" in browser_service._CDP_RELAY_SCRIPT
    assert ("sandbox-1", 3) in browser_service._CDP_INPUT_SOCKET_READY


def test_viewport_stop_clears_persistent_input_relay_state(monkeypatch):
    browser_service._CDP_INPUT_SOCKET_READY.add(("sandbox-1", 8))
    calls = []
    monkeypatch.setattr(
        browser_service,
        "execute_sandbox_argv",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"return_code": 0, "stdout": "", "stderr": ""},
    )

    result = browser_service.viewport_stop("sandbox-1", 8)

    assert result["state"] == "stopped"
    assert ("sandbox-1", 8) not in browser_service._CDP_INPUT_SOCKET_READY
    command = calls[0][0][1][2]
    assert "mcp-browser-input-8.sock" in command


def test_viewport_frame_decodes_latest_jpeg(monkeypatch):
    monkeypatch.setattr(
        browser_service,
        "execute_sandbox_argv",
        lambda *args, **kwargs: {"return_code": 0, "stdout": "aGVsbG8=", "stderr": ""},
    )
    data, mime = browser_service.viewport_frame("sandbox-1", 2)
    assert data == b"hello"
    assert mime == "image/jpeg"


def test_viewport_frame_waits_when_no_frame(monkeypatch):
    monkeypatch.setattr(
        browser_service,
        "execute_sandbox_argv",
        lambda *args, **kwargs: {"return_code": 0, "stdout": "", "stderr": ""},
    )
    data, mime = browser_service.viewport_frame("sandbox-1", 2)
    assert data == b""
    assert mime is None


def test_browser_input_uses_persistent_cdp_relay(monkeypatch):
    calls = []
    monkeypatch.setattr(browser_service, "_ensure_cdp_input", lambda sandbox: None)
    browser_service._CDP_INPUT_SOCKET_READY.add(("sandbox-1", 3))
    monkeypatch.setattr(
        browser_service,
        "execute_sandbox_argv",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"return_code": 0, "stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(
        browser_service,
        "_run_node_script",
        lambda sandbox, script, args, **kwargs: calls.append((sandbox, script, args)) or {"return_code": 0, "stdout": "", "stderr": ""},
    )

    result = browser_service.browser_click("sandbox-1", 3, 10, 20)

    assert result["page_id"] == 3
    assert len(calls) == 1
    assert calls[0][1] == browser_service._CDP_INPUT_PATH
    assert calls[0][2][0].endswith("mcp-browser-input-3.sock")
    assert calls[0][2][1] == "click"
    assert '"x":10.0' in calls[0][2][2]
    assert '"y":20.0' in calls[0][2][2]


def test_browser_input_reuses_socket_without_rechecking_each_event(monkeypatch):
    sandbox = "sandbox-1"
    page_id = 4
    browser_service._CDP_INPUT_SOCKET_READY.add((sandbox, page_id))
    checks = []
    sends = []
    monkeypatch.setattr(browser_service, "_ensure_cdp_input", lambda _: None)
    monkeypatch.setattr(
        browser_service,
        "execute_sandbox_argv",
        lambda *args, **kwargs: checks.append(args) or {"return_code": 0, "stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(
        browser_service,
        "_run_node_script",
        lambda *args, **kwargs: sends.append(args) or {"return_code": 0, "stdout": "", "stderr": ""},
    )

    browser_service.browser_move(sandbox, page_id, 1, 2)
    browser_service.browser_move(sandbox, page_id, 3, 4)

    assert checks == []
    assert len(sends) == 2


def test_browser_input_recovers_when_persistent_relay_dies(monkeypatch):
    sandbox = "sandbox-1"
    page_id = 5
    browser_service._CDP_INPUT_SOCKET_READY.add((sandbox, page_id))
    starts = []
    sends = []
    monkeypatch.setattr(browser_service, "_ensure_cdp_input", lambda _: None)
    monkeypatch.setattr(
        browser_service,
        "_run_node_script",
        lambda *args, **kwargs: sends.append(args) or {
            "return_code": 1 if len(sends) == 1 else 0,
            "stdout": "",
            "stderr": "dead relay" if len(sends) == 1 else "",
        },
    )
    monkeypatch.setattr(
        browser_service,
        "viewport_start",
        lambda *args, **kwargs: starts.append((args, kwargs)) or {"state": "starting"},
    )

    result = browser_service.browser_move(sandbox, page_id, 1, 2)

    assert result["page_id"] == page_id
    assert len(starts) == 1
    assert len(sends) == 2
    assert (sandbox, page_id) in browser_service._CDP_INPUT_SOCKET_READY


def test_cdp_relay_script_has_atomic_frame_writes_and_backpressure():
    script = browser_service._CDP_RELAY_SCRIPT
    assert 'outputPath + ".tmp"' in script
    assert "fs.renameSync(tempFramePath, outputPath)" in script
    assert "Page.screencastFrameAck" in script
    assert "maxFramesInFlight: 1" in script
    assert "everyNthFrame: 4" in script


def test_cdp_input_client_is_unix_socket_based():
    script = browser_service._CDP_INPUT_SCRIPT
    assert 'require("net")' in script
    assert "net.createConnection(socketPath)" in script
    assert "socket.write(JSON.stringify({operation, payload: JSON.parse(payload)}) + \"\\n\")" in script


def test_browser_drag_validates_step_count():
    with pytest.raises(browser_service.BrowserError):
        browser_service.browser_drag("sandbox-1", 1, 0, 0, 10, 10, steps=1)
