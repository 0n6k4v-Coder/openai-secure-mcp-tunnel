from __future__ import annotations

import json
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


PROTOCOL_VERSION = "2026-07-28"


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: Any
    body: bytes


def _jsonrpc_request(
    method: str, request_id: int = 1, params: dict | None = None
) -> bytes:
    request_params = dict(params or {})
    request_params.setdefault(
        "_meta",
        {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientCapabilities": {},
        },
    )
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": request_params,
        }
    ).encode("utf-8")


def _response_messages(result: HTTPResult) -> list[dict]:
    content_type = result.headers.get("Content-Type", "").lower()

    if "text/event-stream" in content_type:
        messages = []
        for line in result.body.decode("utf-8").splitlines():
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if not data:
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                messages.append(payload)
        return messages

    payload = json.loads(result.body)
    assert isinstance(payload, dict)
    return [payload]


def _response_payload(result: HTTPResult) -> dict:
    messages = _response_messages(result)
    responses = [
        payload
        for payload in messages
        if "result" in payload or "error" in payload
    ]
    if not responses:
        pytest.fail(
            "Response contained no JSON-RPC result or error: "
            f"{result.body[:500]!r}"
        )
    return responses[-1]


def _assert_protocol_response(result: HTTPResult) -> dict:
    assert 200 <= result.status < 300, (
        f"Expected a successful MCP response; HTTP {result.status}: "
        f"{result.body[:500]!r}"
    )
    payload = _response_payload(result)
    assert payload.get("jsonrpc") == "2.0"
    assert "result" in payload or "error" in payload
    return payload


def _assert_rejected(result: HTTPResult) -> None:
    if result.status >= 400:
        return

    payload = _response_payload(result)
    assert "error" in payload, (
        f"Invalid request was not rejected: HTTP {result.status}, "
        f"response={payload!r}"
    )


@pytest.fixture
def raw_mcp_request(mcp_settings):
    def send(
        body: bytes,
        *,
        host: str | None = None,
        origin: str | None = None,
        timeout: float = 10.0,
    ) -> HTTPResult:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Host": host or mcp_settings.host_header,
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }

        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None

        if isinstance(payload, dict) and isinstance(payload.get("method"), str):
            headers["Mcp-Method"] = payload["method"]

        if origin is not None:
            headers["Origin"] = origin

        request = Request(
            mcp_settings.url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(request, timeout=timeout) as response:
                return HTTPResult(
                    response.status,
                    response.headers,
                    response.read(),
                )
        except HTTPError as exc:
            return HTTPResult(exc.code, exc.headers, exc.read())

    return send


def test_MCP_TRANSPORT_001_connect_to_configured_endpoint(mcp_client) -> None:
    result = mcp_client.run(lambda client: client.list_tools())
    assert result.tools
    assert all(tool.name for tool in result.tools)


def test_MCP_TRANSPORT_002_initialize_client(mcp_client) -> None:
    protocol_version, server_info, capabilities = mcp_client.run(
        lambda client: (
            client.protocol_version,
            client.server_info,
            client.server_capabilities,
        )
    )
    assert protocol_version
    assert server_info is not None
    assert capabilities is not None


def test_MCP_TRANSPORT_003_verify_server_identity(mcp_client) -> None:
    server_info = mcp_client.run(lambda client: client.server_info)
    assert server_info is not None
    assert server_info.name == "local-computer"
    assert server_info.version == "0.1.0"


def test_MCP_TRANSPORT_004_verify_protocol_version(mcp_client) -> None:
    assert mcp_client.run(lambda client: client.protocol_version) == PROTOCOL_VERSION


def test_MCP_TRANSPORT_005_verify_tool_capability(mcp_client) -> None:
    capabilities = mcp_client.run(lambda client: client.server_capabilities)
    assert capabilities is not None
    assert capabilities.tools is not None


def test_MCP_TRANSPORT_006_valid_tool_list(mcp_client) -> None:
    result = mcp_client.run(lambda client: client.list_tools())
    names = [tool.name for tool in result.tools]
    assert names
    assert len(names) == len(set(names))


def test_MCP_TRANSPORT_007_valid_tool_call(raw_mcp_request) -> None:
    params = {
        "name": "get_system_info",
        "arguments": {},
        "_meta": {
            "progressToken": 7,
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientCapabilities": {},
        },
    }
    response = raw_mcp_request(_jsonrpc_request("tools/call", params=params))
    payload = _assert_protocol_response(response)
    assert "result" in payload

    progress_notifications = [
        message
        for message in _response_messages(response)
        if message.get("method") == "notifications/progress"
    ]
    assert progress_notifications, (
        "Tool call did not emit an MCP progress notification despite a progressToken."
    )
    assert all(
        message.get("params", {}).get("progressToken") == 7
        for message in progress_notifications
    )


def test_MCP_TRANSPORT_008_malformed_protocol_request(raw_mcp_request) -> None:
    result = raw_mcp_request(b'{"jsonrpc":"2.0","id":1}')
    _assert_rejected(result)


def test_MCP_TRANSPORT_009_unsupported_method(raw_mcp_request) -> None:
    result = raw_mcp_request(_jsonrpc_request("method/that/does/not/exist"))
    _assert_rejected(result)


def test_MCP_TRANSPORT_010_invalid_tool_call_envelope(raw_mcp_request) -> None:
    result = raw_mcp_request(_jsonrpc_request("tools/call", params={}))
    _assert_rejected(result)


def test_MCP_TRANSPORT_011_invalid_json_body(raw_mcp_request) -> None:
    result = raw_mcp_request(b'{"jsonrpc":"2.0","id":')
    _assert_rejected(result)


def test_MCP_TRANSPORT_012_oversized_request_body(raw_mcp_request) -> None:
    body = (
        b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{},"padding":"'
        + b"x" * (1024 * 1024)
        + b'"}'
    )
    result = raw_mcp_request(body, timeout=30.0)
    assert result.status == 413, (
        f"Expected HTTP 413 for oversized body, received HTTP {result.status}: "
        f"{result.body[:300]!r}"
    )


def test_MCP_TRANSPORT_013_allowed_host(raw_mcp_request) -> None:
    result = raw_mcp_request(_jsonrpc_request("tools/list"))
    payload = _assert_protocol_response(result)
    assert "result" in payload


def test_MCP_TRANSPORT_014_unapproved_host_rejected(raw_mcp_request) -> None:
    result = raw_mcp_request(
        _jsonrpc_request("tools/list"),
        host="unapproved.invalid",
    )
    assert result.status >= 400, (
        f"Unapproved Host was not rejected: HTTP {result.status}, "
        f"{result.body[:300]!r}"
    )


def test_MCP_TRANSPORT_015_dns_rebinding_origin_rejected(raw_mcp_request) -> None:
    result = raw_mcp_request(
        _jsonrpc_request("tools/list"),
        origin="https://unapproved.invalid",
    )
    assert result.status >= 400, (
        f"Unapproved Origin was not rejected: HTTP {result.status}, "
        f"{result.body[:300]!r}"
    )


def test_MCP_TRANSPORT_016_sequential_requests(mcp_client) -> None:
    results = [mcp_client.call_tool("get_system_info") for _ in range(3)]
    assert len(results) == 3
    assert all(result["operating_system"] for result in results)
    assert all(result["python_version"] for result in results)


def test_MCP_TRANSPORT_017_concurrent_requests(mcp_client_factory) -> None:
    def call_system_info() -> dict:
        return mcp_client_factory().call_tool("get_system_info")

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: call_system_info(), range(4)))

    assert len(results) == 4
    assert all(result["operating_system"] for result in results)
    assert all(result["python_version"] for result in results)


def test_MCP_TRANSPORT_018_stateless_http_behavior(raw_mcp_request) -> None:
    first = raw_mcp_request(_jsonrpc_request("tools/list", request_id=1))
    second = raw_mcp_request(_jsonrpc_request("tools/list", request_id=2))
    _assert_protocol_response(first)
    _assert_protocol_response(second)
    assert first.headers.get("Mcp-Session-Id") is None
    assert second.headers.get("Mcp-Session-Id") is None


def test_MCP_TRANSPORT_019_restart_and_reconnect() -> None:
    pytest.skip(
        "BLOCKED: the server binds to fixed port 8000 and the repository has no "
        "test-owned server lifecycle fixture. Restarting an external service is unsafe."
    )


def test_MCP_TRANSPORT_020_server_unavailable_returns_connection_failure() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        unused_port = listener.getsockname()[1]

    request = Request(
        f"http://127.0.0.1:{unused_port}/mcp",
        data=_jsonrpc_request("tools/list"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Host": "mcp-server:8000",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": "tools/list",
        },
        method="POST",
    )

    with pytest.raises(URLError) as error:
        with urlopen(request, timeout=3.0):
            pass

    assert not isinstance(error.value, HTTPError), (
        "Expected connection failure, not HTTP response."
    )
