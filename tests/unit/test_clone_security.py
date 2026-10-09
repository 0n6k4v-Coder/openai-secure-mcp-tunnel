from __future__ import annotations

import socket
import subprocess

import pytest

from local_mcp_server.clone import chrome
from local_mcp_server.clone.pipeline import _safe_relative_project_path, _sanitize_html_fragment, create_clone_manifest, generate_project


def _dns_answer(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]


def test_browser_policy_rejects_private_dns_before_policy_update(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(chrome.socket, "getaddrinfo", lambda *args, **kwargs: _dns_answer("10.0.0.12"))
    monkeypatch.setattr(chrome.subprocess, "run", fake_run)
    with pytest.raises(chrome.BrowserError, match="non-public"):
        chrome._ensure_browser_endpoint_allowed("clone-test", "https://example.com/")
    assert not called


def test_browser_policy_adds_only_exact_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(chrome, "_ALLOWED_ENDPOINTS_CACHE", set())
    monkeypatch.setattr(chrome.socket, "getaddrinfo", lambda *args, **kwargs: _dns_answer("93.184.216.34"))

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(chrome.subprocess, "run", fake_run)
    chrome._ensure_browser_endpoint_allowed("clone-test", "https://example.com/path")
    assert len(calls) == 1
    assert "example.com:443" in calls[0]
    assert not any("*." in arg for arg in calls[0])


def test_browser_policy_failure_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chrome, "_ALLOWED_ENDPOINTS_CACHE", set())
    monkeypatch.setattr(chrome.socket, "getaddrinfo", lambda *args, **kwargs: _dns_answer("93.184.216.34"))
    monkeypatch.setattr(chrome.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 1, "", "denied"))
    with pytest.raises(chrome.BrowserError, match="policy update failed"):
        chrome._ensure_browser_endpoint_allowed("clone-test", "https://example.com/")
    assert ("clone-test", "example.com", 443) not in chrome._ALLOWED_ENDPOINTS_CACHE


def test_generated_html_strips_scripts_handlers_and_unsafe_urls() -> None:
    result = _sanitize_html_fragment('<h1 onclick="x()">Hello</h1><script>alert(1)</script><a href="javascript:alert(2)">go</a>')
    assert '<h1>Hello</h1>' in result
    assert '<script' not in result and 'onclick=' not in result and 'javascript:' not in result


def test_output_paths_cannot_escape_workspace() -> None:
    for path in ("../outside", "/tmp/outside", "clones/../../etc", r"clones\..\outside"):
        with pytest.raises(ValueError):
            _safe_relative_project_path(path, field="output_dir")
    assert _safe_relative_project_path("clones/site") == "clones/site"


def test_manifest_and_generation_require_a_real_source_url() -> None:
    with pytest.raises(ValueError, match="valid HTTP"):
        create_clone_manifest(inspect_runtime={"title": "No URL"})
    with pytest.raises(ValueError, match="valid HTTP"):
        generate_project("clone-test", manifest={"site": {"title": "No URL"}})
