from __future__ import annotations

import pytest

from local_mcp_server.cli import lifecycle


@pytest.mark.parametrize(
    ("variable", "value", "expected"),
    [
        ("MCP_PORT", "18000", "http://127.0.0.1:18000/healthz"),
        ("OPENSHELL_HEALTH_PORT", "18081", "http://127.0.0.1:18081/readyz"),
    ],
)
def test_health_urls_follow_runtime_published_ports(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
    expected: str,
) -> None:
    monkeypatch.setenv(variable, value)

    actual = (
        lifecycle._mcp_health_url()
        if variable == "MCP_PORT"
        else lifecycle._gateway_health_url()
    )

    assert actual == expected


@pytest.mark.parametrize("value", ["0", "65536", "-1", "not-a-port"])
def test_invalid_runtime_port_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("MCP_PORT", value)

    with pytest.raises(lifecycle.LifecycleError, match="MCP_PORT"):
        lifecycle._mcp_health_url()


def test_mcp_health_request_uses_allowed_internal_host() -> None:
    request = lifecycle._health_request("http://127.0.0.1:18000/healthz")

    assert request.get_header("Host") == "127.0.0.1:8000"


def test_gateway_health_request_does_not_override_host_header() -> None:
    request = lifecycle._health_request("http://127.0.0.1:18081/readyz")

    assert request.get_header("Host") is None
