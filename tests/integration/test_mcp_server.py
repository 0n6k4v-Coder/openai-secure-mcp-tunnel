from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

from .conftest import MCPIntegrationClient

EXPECTED_TOOLS = {
    "get_system_info",
    "create_sandbox",
    "list_sandboxes",
    "sandbox_status",
    "sandbox_logs",
    "start_sandbox",
    "stop_sandbox",
    "restart_sandbox",
    "repair_sandbox",
    "recreate_sandbox",
    "delete_sandbox",
    "execute_sandbox_command",
    "list_workspace_files",
    "read_workspace_text_file",
    "create_workspace_file",
    "write_workspace_file",
    "create_workspace_directory",
    "rename_workspace_path",
    "delete_workspace_file",
    "delete_workspace_directory",
    "list_authorized_host_workspaces",
    "request_tool_installation",
    "execute_chrome_devtools_command",
}


@pytest.mark.integration
def test_mcp_health_endpoint() -> None:
    if os.environ.get("RUN_MCP_INTEGRATION") != "1":
        pytest.skip("Set RUN_MCP_INTEGRATION=1 to run MCP integration tests.")

    url = os.environ.get(
        "MCP_HEALTH_URL",
        "http://127.0.0.1:8000/healthz",
    )

    request = urllib.request.Request(
        url,
        headers={
            "Host": os.environ.get(
                "MCP_INTEGRATION_HOST",
                "mcp-server:8000",
            ),
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=5,
        ) as response:
            body = response.read().decode("utf-8")
            status = response.status
    except urllib.error.URLError as exc:
        pytest.fail(f"MCP health endpoint is unreachable: {exc}")

    assert status == 200

    payload = json.loads(body)

    assert payload["status"] == "ok"
    assert payload["service"] == "local-computer"
    assert payload["version"] == "0.1.0"


@pytest.mark.integration
def test_mcp_negotiates_current_protocol(
    mcp_client: MCPIntegrationClient,
) -> None:
    def inspect_client(client: object):
        return (
            client.protocol_version,
            client.server_info,
            client.server_capabilities,
        )

    protocol_version, server_info, capabilities = mcp_client.run(inspect_client)

    assert protocol_version == "2026-07-28"

    assert server_info is not None
    assert server_info.name == "local-computer"
    assert server_info.version == "0.1.0"

    assert capabilities.tools is not None


@pytest.mark.integration
def test_mcp_exposes_current_tool_surface(
    mcp_client: MCPIntegrationClient,
) -> None:
    def list_tools(client: object):
        return client.list_tools()

    result = mcp_client.run(list_tools)

    actual_tools = {tool.name for tool in result.tools}

    assert actual_tools == EXPECTED_TOOLS


@pytest.mark.integration
def test_mcp_tool_call_round_trip(
    mcp_client: MCPIntegrationClient,
) -> None:
    result = mcp_client.call_tool("get_system_info")

    assert isinstance(result, dict)
    assert result["operating_system"]
    assert result["python_version"]
    assert result["python_implementation"]


@pytest.mark.integration
def test_installation_tool_rejects_unapproved_command(
    mcp_client: MCPIntegrationClient,
) -> None:
    result = mcp_client.call_tool_expect_error(
        "request_tool_installation",
        {
            "sandbox_name": "integration-security-check",
            "tool_name": "test-tool",
            "version": "1.0.0",
            "source": "integration-test",
            "install_command": "true",
            "reason": "Integration test must not execute arbitrary commands.",
        },
    )

    assert result.is_error is True
