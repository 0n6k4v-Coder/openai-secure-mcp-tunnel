from __future__ import annotations

import pytest

from local_mcp_server.sandbox import policy


def test_build_sandbox_spec_emits_expected_workspace_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "host_path": "/tmp/test-workspace",
            "volume_name": "mcp-ws-testvolume123",
            "target": "/workspace/project",
            "read_only": False,
        },
    )

    spec = policy.build_sandbox_spec("ws_test")

    assert spec.policy is not None


def test_build_sandbox_spec_emits_narrow_network_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "host_path": "/tmp/test-workspace",
            "volume_name": "mcp-ws-testvolume123",
            "target": "/workspace/project",
            "read_only": False,
        },
    )

    spec = policy.build_sandbox_spec("ws_test")

    assert set(spec.policy.network_policies) == {
        "npm_registry",
        "browser_cdp",
    }

    npm_policy = spec.policy.network_policies["npm_registry"]
    assert npm_policy.name == "npm-registry"

    npm_endpoint = npm_policy.endpoints[0]
    assert npm_endpoint.host == "registry.npmjs.org"
    assert npm_endpoint.port == 443
    assert npm_endpoint.protocol == "rest"

    npm_binary = npm_policy.binaries[0]
    assert npm_binary.path == "/usr/local/bin/node"

    browser_policy = spec.policy.network_policies["browser_cdp"]
    assert browser_policy.name == "browser-cdp"

    browser_endpoint = browser_policy.endpoints[0]
    assert browser_endpoint.host == "198.18.0.2"
    assert browser_endpoint.port == 9222
    assert browser_endpoint.protocol == "tcp"

    browser_binary = browser_policy.binaries[0]
    assert browser_binary.path == "/usr/local/bin/node"


def test_build_sandbox_spec_emits_expected_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "host_path": "/tmp/test-workspace",
            "volume_name": "mcp-ws-testvolume123",
            "target": "/workspace/project",
            "read_only": False,
        },
    )

    spec = policy.build_sandbox_spec("ws_test")

    assert spec is not None


def test_build_sandbox_spec_emits_expected_resource_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "host_path": "/tmp/test-workspace",
            "volume_name": "mcp-ws-testvolume123",
            "target": "/workspace/project",
            "read_only": False,
        },
    )

    spec = policy.build_sandbox_spec("ws_test")

    assert spec is not None