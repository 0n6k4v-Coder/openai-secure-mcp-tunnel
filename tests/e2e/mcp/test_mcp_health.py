from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

import pytest

EXPECTED_SERVICE = "local-computer"
EXPECTED_VERSION = "0.1.0"
EXPECTED_FIELDS = {"status", "service", "version", "instance_id", "pid"}


def _health_url(settings: Any) -> str:
    parsed = urlsplit(settings.url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/healthz", "", ""))


def _get_health(
    settings: Any,
    *,
    host: str | None = None,
    timeout: float = 5.0,
) -> tuple[int, Any, bytes]:
    request = Request(
        _health_url(settings),
        headers={
            "Accept": "application/json",
            "Host": host or settings.host_header,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read()


@pytest.fixture(autouse=True)
def wait_for_health_endpoint(mcp_settings: Any) -> None:
    """Wait for the freshly started container to serve health requests."""
    deadline = time.monotonic() + 20.0
    last_error = "endpoint did not respond"
    while time.monotonic() < deadline:
        try:
            status, _headers, body = _get_health(mcp_settings, timeout=1.0)
            if status == 200:
                return
            last_error = f"HTTP {status}: {body[:200]!r}"
        except OSError as exc:
            last_error = str(exc)
        time.sleep(0.25)
    pytest.fail(
        f"MCP health endpoint did not become ready within 20 seconds: {last_error}"
    )


def _health_payload(settings: Any) -> dict[str, Any]:
    status, headers, body = _get_health(settings)
    assert status == 200, (
        f"Expected HTTP 200 from GET /healthz, received {status}: {body[:500]!r}"
    )
    content_type = headers.get("Content-Type", "")
    assert "application/json" in content_type.lower(), (
        f"Expected JSON Content-Type, received {content_type!r}"
    )
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssertionError(
            f"GET /healthz returned invalid JSON: {body[:500]!r}"
        ) from exc
    assert isinstance(payload, dict), (
        f"Expected a JSON object, received {type(payload).__name__}"
    )
    return payload


@pytest.mark.integration
def test_MCP_HEALTH_001_get_health_endpoint(mcp_settings: Any) -> None:
    status, _headers, body = _get_health(mcp_settings)
    assert status == 200, (
        f"Expected HTTP 200 from GET /healthz, received {status}: {body[:500]!r}"
    )


@pytest.mark.integration
def test_MCP_HEALTH_002_validate_health_response_json(
    mcp_settings: Any,
) -> None:
    payload = _health_payload(mcp_settings)
    missing_fields = EXPECTED_FIELDS - payload.keys()
    assert not missing_fields, (
        f"Health response is missing fields: {sorted(missing_fields)}"
    )


@pytest.mark.integration
def test_MCP_HEALTH_003_validate_health_status(
    mcp_settings: Any,
) -> None:
    payload = _health_payload(mcp_settings)
    assert payload.get("status") == "ok", (
        f"Expected status 'ok', received {payload.get('status')!r}"
    )


@pytest.mark.integration
def test_MCP_HEALTH_004_validate_service_identity(
    mcp_settings: Any,
) -> None:
    payload = _health_payload(mcp_settings)
    assert payload.get("service") == EXPECTED_SERVICE, (
        f"Expected service {EXPECTED_SERVICE!r}, received {payload.get('service')!r}"
    )
    assert payload.get("version") == EXPECTED_VERSION, (
        f"Expected version {EXPECTED_VERSION!r}, received {payload.get('version')!r}"
    )


@pytest.mark.integration
def test_MCP_HEALTH_005_validate_instance_metadata(
    mcp_settings: Any,
) -> None:
    payload = _health_payload(mcp_settings)
    instance_id = payload.get("instance_id")
    assert isinstance(instance_id, str) and instance_id.strip(), (
        "Expected instance_id to be a non-empty string."
    )
    pid = payload.get("pid")
    assert isinstance(pid, int) and not isinstance(pid, bool) and pid > 0, (
        f"Expected pid to be a positive integer, received {pid!r}"
    )


@pytest.mark.integration
def test_MCP_HEALTH_006_repeated_health_requests(
    mcp_settings: Any,
) -> None:
    for request_number in range(1, 6):
        payload = _health_payload(mcp_settings)
        assert payload.get("status") == "ok", (
            f"Health request {request_number} did not report status 'ok'."
        )


@pytest.mark.integration
def test_MCP_HEALTH_007_allowed_host(mcp_settings: Any) -> None:
    status, _headers, body = _get_health(
        mcp_settings,
        host=mcp_settings.host_header,
    )
    assert status == 200, (
        f"Expected configured Host to be accepted, received {status}: {body[:500]!r}"
    )


@pytest.mark.integration
def test_MCP_HEALTH_008_disallowed_host_rejected(
    mcp_settings: Any,
) -> None:
    status, _headers, body = _get_health(
        mcp_settings,
        host="unapproved.invalid",
    )
    assert 400 <= status < 500, (
        "Expected a disallowed Host to be rejected with HTTP 4xx, "
        f"received {status}: {body[:500]!r}"
    )
