from __future__ import annotations

from local_mcp_server.sandbox import policy


def test_default_profile_allows_only_package_index_hosts_for_package_managers() -> None:
    spec = policy.build_sandbox_spec()
    assert set(spec.policy.network_policies) == {
        "npm_registry",
        "python_package_index",
    }

    python_policy = spec.policy.network_policies["python_package_index"]
    assert python_policy.name == "python-package-index"
    assert {endpoint.host for endpoint in python_policy.endpoints} == {
        "pypi.org",
        "files.pythonhosted.org",
    }
    for endpoint in python_policy.endpoints:
        assert endpoint.port == 443
        assert endpoint.protocol == "rest"
        assert {
            (rule.allow.method, rule.allow.path) for rule in endpoint.rules
        } == {("GET", "/**"), ("HEAD", "/**")}
    assert [binary.path for binary in python_policy.binaries] == [policy._UV_BINARY]


def test_browser_profile_does_not_receive_package_index_policies() -> None:
    spec = policy.build_sandbox_spec(profile="browser")
    assert set(spec.policy.network_policies) == {"browser_web"}
