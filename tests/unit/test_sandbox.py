from __future__ import annotations

import pytest

from local_mcp_server.sandbox import policy


def _workspace_grant(workspace_id: str) -> dict[str, object]:
    return {
        "workspace_id": workspace_id,
        "host_path": "/tmp/test-workspace",
        "volume_name": "mcp-ws-testvolume123",
        "target": "/workspace/project",
        "read_only": False,
    }


def test_build_sandbox_spec_emits_expected_workspace_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        _workspace_grant,
    )

    spec = policy.build_sandbox_spec("ws_test")

    assert spec.policy is not None


def test_default_sandbox_does_not_depend_on_external_browser_relay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        _workspace_grant,
    )

    spec = policy.build_sandbox_spec("ws_test")

    assert set(spec.policy.network_policies) == {
        "npm_registry",
    }


def test_default_sandbox_uses_default_image_and_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        _workspace_grant,
    )

    spec = policy.build_sandbox_spec(
        "ws_test",
        profile="default",
    )

    assert spec.template.image == policy.SANDBOX_IMAGE
    assert list(spec.command) == [
        "sleep",
        "infinity",
    ]


def test_browser_sandbox_uses_browser_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        _workspace_grant,
    )

    spec = policy.build_sandbox_spec(
        "ws_test",
        profile="browser",
    )

    assert spec.template.image == policy.BROWSER_SANDBOX_IMAGE
    assert list(spec.command) == [
        "/usr/bin/dumb-init",
        "--",
        "/usr/local/bin/browser-runtime",
    ]


def test_browser_sandbox_has_browser_specific_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        _workspace_grant,
    )

    monkeypatch.setenv(
        "BROWSER_ALLOWED_ENDPOINTS",
        "host.openshell.internal:4173,mtioon.com:443",
    )

    spec = policy.build_sandbox_spec(
        "ws_test",
        profile="browser",
    )

    assert set(spec.policy.network_policies) == {
        "browser_web",
    }

    browser_policy = spec.policy.network_policies["browser_web"]

    assert browser_policy.name == "browser-web"

    assert {
        (endpoint.host, endpoint.port, endpoint.protocol)
        for endpoint in browser_policy.endpoints
    } == {
        ("host.openshell.internal", 4173, ""),
        ("mtioon.com", 443, ""),
    }

    assert browser_policy.binaries[0].path == "/opt/chrome/chrome"


def test_browser_profile_is_validated() -> None:
    assert policy.validate_profile("default") == "default"
    assert policy.validate_profile("browser") == "browser"

    with pytest.raises(ValueError):
        policy.validate_profile("unknown")