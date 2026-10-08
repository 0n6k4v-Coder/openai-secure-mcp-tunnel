from __future__ import annotations

import os
import time

import pytest

from local_mcp_server.browser.service import (
    browser_click,
    browser_evaluate,
    browser_key,
    browser_move,
    browser_scroll,
    browser_type,
    execute_sandbox_argv,
    open_page,
    viewport_frame,
    viewport_start,
    viewport_stop,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def live_browser():
    if not os.environ.get("RUN_BROWSER_INTEGRATION"):
        pytest.skip("Set RUN_BROWSER_INTEGRATION=1 to run against a live browser sandbox.")

    sandbox = os.environ.get("BROWSER_INTEGRATION_SANDBOX", "web-cloning")
    opened = open_page(sandbox, "https://example.com")
    assert opened["url"] == "https://example.com"
    result = opened["result"]
    page_id = int(result.get("pageId") or result.get("page_id"))

    started = viewport_start(sandbox, page_id, width=1024, height=768, quality=60)
    assert started["state"] == "starting"

    try:
        yield sandbox, page_id
    finally:
        viewport_stop(sandbox, page_id)


def wait_for_frame(sandbox: str, page_id: int) -> tuple[bytes, str | None]:
    for _ in range(30):
        frame, mime = viewport_frame(sandbox, page_id)
        if frame:
            return frame, mime
        time.sleep(0.1)
    return b"", None


def test_live_screencast_stays_available_during_input_burst(live_browser):
    sandbox, page_id = live_browser

    frame, mime = wait_for_frame(sandbox, page_id)
    assert frame
    assert mime == "image/jpeg"

    browser_evaluate(
        sandbox,
        page_id,
        """
        () => {
          document.body.innerHTML = `
            <input id="live-input" style="position:fixed;left:20px;top:20px;width:240px;height:32px">
            <button id="live-button" style="position:fixed;left:20px;top:70px;width:120px;height:40px">Click</button>
            <div id="live-output" style="position:fixed;left:20px;top:125px"></div>
          `;
          window.liveClicks = 0;
          document.querySelector("#live-button").addEventListener("click", () => {
            window.liveClicks += 1;
            document.querySelector("#live-output").textContent = String(window.liveClicks);
          });
          document.querySelector("#live-input").focus();
          return true;
        }
        """,
    )

    browser_type(sandbox, page_id, "hello")
    browser_key(sandbox, page_id, "Control+A")
    browser_type(sandbox, page_id, "hello world")
    browser_click(sandbox, page_id, 80, 90)

    state = browser_evaluate(
        sandbox,
        page_id,
        "() => ({ value: document.querySelector('#live-input').value, clicks: window.liveClicks })",
    )
    assert state["result"]["value"] == "hello world"
    assert state["result"]["clicks"] == 1

    # Multiple input events must continue using the same page-scoped relay socket.
    for x in range(30, 331, 15):
        browser_move(sandbox, page_id, x, 150)

    socket = f"/tmp/mcp-browser-input-{page_id}.sock"
    socket_check = execute_sandbox_argv(
        sandbox,
        ["sh", "-c", f"test -S {socket}"],
        timeout_seconds=5,
    )
    assert socket_check["return_code"] == 0

    frame, mime = wait_for_frame(sandbox, page_id)
    assert frame
    assert mime == "image/jpeg"


def test_live_scroll_updates_shared_page_state(live_browser):
    sandbox, page_id = live_browser

    browser_evaluate(
        sandbox,
        page_id,
        """
        () => {
          document.body.innerHTML = '<div style="height:6000px">scroll target</div>';
          window.scrollTo(0, 0);
          return window.scrollY;
        }
        """,
    )

    before = browser_evaluate(sandbox, page_id, "() => window.scrollY")
    browser_scroll(sandbox, page_id, 0, 800, x=100, y=100)
    after = browser_evaluate(sandbox, page_id, "() => window.scrollY")

    assert before["result"] == 0
    assert after["result"] > 0
