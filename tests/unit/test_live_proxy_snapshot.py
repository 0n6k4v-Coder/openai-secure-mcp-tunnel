from __future__ import annotations

import pytest

from local_mcp_server.clone.live_proxy import (
    _UNIVERSAL_RUNTIME_SHIM,
    _normalize_relative_path,
    create_live_proxy_snapshot,
)


def test_normalize_relative_path() -> None:
    assert _normalize_relative_path("apps/demo/live-proxy") == "apps/demo/live-proxy"
    assert _normalize_relative_path("apps/demo/clone") == "apps/demo/clone"
    assert _normalize_relative_path("clones/test") == "clones/test"

    with pytest.raises(ValueError, match="canonical relative path"):
        _normalize_relative_path("/absolute/path")

    with pytest.raises(ValueError, match="canonical relative path"):
        _normalize_relative_path("../outside")

    with pytest.raises(ValueError, match="canonical relative path"):
        _normalize_relative_path("apps/../demo")


def test_runtime_shim_content() -> None:
    assert "Universal Snapshot Runtime Shim" in _UNIVERSAL_RUNTIME_SHIM
    assert "rehydrateIslands" in _UNIVERSAL_RUNTIME_SHIM
    assert "setupDismissableBanners" in _UNIVERSAL_RUNTIME_SHIM
    assert "ssr" in _UNIVERSAL_RUNTIME_SHIM


def test_create_live_proxy_snapshot_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    executed_commands: list[list[str]] = []

    def fake_evaluate(sandbox_name: str, page_id: int, script: str) -> dict[str, object]:
        if "html" in script:
            return {
                "result": {
                    "html": "<html><head><meta http-equiv='Content-Security-Policy' content='default-src self'></head><body><section id='pricing' style='opacity: 0;'><img src='/images/pricing/free.svg'></section></body></html>",
                    "title": "Mock Title",
                    "origin": "https://example.com",
                    "url": "https://example.com/",
                    "scriptUrls": ["/_astro/test.js"],
                    "apiRequests": ["https://example.com/api/plans"],
                }
            }
        return {"result": {"scrolled": True}}

    def fake_execute_sandbox_argv(sandbox_name: str, argv: list[str], **kwargs: object) -> dict[str, object]:
        executed_commands.append(argv)
        return {"return_code": 0, "stdout": "", "stderr": ""}

    def fake_format_text_in_sandbox(sandbox_name: str, path: str, content: str) -> tuple[str, dict[str, str]]:
        return content, {"formatter": "none"}

    monkeypatch.setattr("local_mcp_server.clone.live_proxy.evaluate", fake_evaluate)
    monkeypatch.setattr(
        "local_mcp_server.clone.live_proxy.execute_sandbox_argv", fake_execute_sandbox_argv
    )
    monkeypatch.setattr(
        "local_mcp_server.clone.live_proxy.format_text_in_sandbox", fake_format_text_in_sandbox
    )

    result = create_live_proxy_snapshot(
        "demo-sandbox",
        2,
        "apps/demo/live-proxy",
        prepare_scroll=True,
        download_module_chunks=True,
    )

    assert result["status"] == "completed"
    assert result["sandbox_name"] == "demo-sandbox"
    assert result["output_dir"] == "apps/demo/live-proxy"
    assert result["runtime_shim_injected"] is True
    assert result["downloaded_chunks_count"] == 1
    assert "api/plans" in result["mocked_apis"]

    # Verify mkdir and write commands
    cmds_str = [" ".join(cmd) for cmd in executed_commands]
    assert any("mkdir -p /workspace/project/apps/demo/live-proxy" in cmd for cmd in cmds_str)
    assert any("curl" in cmd and "_astro/test.js" in cmd for cmd in cmds_str)
