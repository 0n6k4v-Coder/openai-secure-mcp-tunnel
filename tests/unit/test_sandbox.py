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


def test_sandbox_name_max_length() -> None:
    valid_name = "a" * policy.MAX_SANDBOX_NAME_LENGTH
    assert policy.validate_name(valid_name) == valid_name

    with pytest.raises(ValueError, match="at most 19 characters"):
        policy.validate_name("a" * (policy.MAX_SANDBOX_NAME_LENGTH + 1))


def test_build_sandbox_spec_without_workspace_is_standalone() -> None:
    spec = policy.build_sandbox_spec()

    assert spec.policy is not None
    assert not spec.template.driver_config


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
    assert spec.template.driver_config["docker"]["mounts"] == [
        {
            "type": "volume",
            "source": "mcp-ws-testvolume123",
            "target": "/workspace/project",
            "read_only": False,
        }
    ]


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

    npm_policy = spec.policy.network_policies["npm_registry"]

    assert npm_policy.name == "npm-registry"

    npm_endpoint = npm_policy.endpoints[0]
    enforcement_field = npm_endpoint.DESCRIPTOR.fields_by_name["enforcement"]
    enforce_value = enforcement_field.enum_type.values_by_name[
        "NETWORK_ENFORCEMENT_MODE_ENFORCE"
    ].number

    assert (
        npm_endpoint.host,
        npm_endpoint.port,
        npm_endpoint.protocol,
        npm_endpoint.enforcement,
    ) == (
        "registry.npmjs.org",
        443,
        "rest",
        enforce_value,
    )

    assert npm_endpoint.allow_encoded_slash is True

    assert {(rule.allow.method, rule.allow.path) for rule in npm_endpoint.rules} == {
        ("GET", "/**"),
        ("HEAD", "/**"),
        ("OPTIONS", "/**"),
        ("POST", "/-/npm/v1/security/advisories/bulk"),
        ("POST", "/-/npm/v1/security/audits/quick"),
    }

    assert npm_policy.binaries[0].path == policy._NPM_NODE_BINARY


def test_default_sandbox_uses_default_image_and_command() -> None:
    spec = policy.build_sandbox_spec(
        profile="default",
    )

    assert spec.template.image == policy.SANDBOX_IMAGE

    assert list(spec.command) == [
        "sleep",
        "infinity",
    ]

    assert list(spec.policy.filesystem.read_write)[-1] == (
        policy.SANDBOX_WORKSPACE_ROOT
    )


def test_browser_sandbox_uses_browser_image() -> None:
    spec = policy.build_sandbox_spec(
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
    monkeypatch.setenv(
        "BROWSER_ALLOWED_ENDPOINTS",
        "host.openshell.internal:4173,mtioon.com:443",
    )

    spec = policy.build_sandbox_spec(
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
    assert browser_policy.binaries[1].path == "/usr/bin/curl"


def test_browser_profile_is_validated() -> None:
    assert policy.validate_profile("default") == "default"
    assert policy.validate_profile("browser") == "browser"

    with pytest.raises(ValueError):
        policy.validate_profile("unknown")
