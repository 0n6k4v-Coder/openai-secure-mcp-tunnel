from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

import pytest

from .conftest import _call_error, _call_ok


def _server_hostname(mcp_settings) -> str:
    parsed = urlsplit(mcp_settings.url)
    health_url = urlunsplit((parsed.scheme, parsed.netloc, "/healthz", "", ""))
    request = Request(
        health_url,
        headers={"Accept": "application/json", "Host": mcp_settings.host_header},
        method="GET",
    )
    try:
        with urlopen(request, timeout=5.0) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        raise AssertionError(f"MCP health check returned HTTP {exc.code}") from exc
    return str(payload["instance_id"]).split(":", 1)[0]


@pytest.mark.integration
def test_MCP_SBX_050_execute_harmless_command(mcp_client, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(
        mcp_client, "execute_sandbox_command", {"name": name, "command": "true"}
    )
    assert isinstance(result, dict)
    assert result["return_code"] == 0


@pytest.mark.integration
def test_MCP_SBX_051_command_output_is_returned(mcp_client, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(
        mcp_client,
        "execute_sandbox_command",
        {"name": name, "command": "printf '%s' 'mcp-e2e-output'"},
    )
    assert result["stdout"] == "mcp-e2e-output"
    assert result["return_code"] == 0


@pytest.mark.integration
def test_MCP_SBX_052_nonzero_command_exit_is_preserved(mcp_client, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(
        mcp_client,
        "execute_sandbox_command",
        {
            "name": name,
            "command": "printf '%s' 'expected-nonzero'; exit 7",
        },
    )
    assert result["stdout"] == "expected-nonzero"
    assert result["return_code"] == 7


@pytest.mark.integration
def test_MCP_SBX_053_shell_special_characters_are_passed_as_command_text(
    mcp_client, created_sandbox
):
    name, _ = created_sandbox
    result = _call_ok(
        mcp_client,
        "execute_sandbox_command",
        {"name": name, "command": "printf '%s' 'space ; $HOME *'"},
    )
    assert result["stdout"] == "space ; $HOME *"
    assert result["return_code"] == 0


@pytest.mark.integration
def test_MCP_SBX_054_command_in_missing_sandbox_fails(mcp_client, missing_sandbox_name):
    assert _call_error(
        mcp_client,
        "execute_sandbox_command",
        {"name": missing_sandbox_name, "command": "printf '%s' 'must-not-run'"},
    ).strip()


@pytest.mark.integration
def test_MCP_SBX_055_command_requires_name_and_command(mcp_client):
    missing_name = _call_error(
        mcp_client, "execute_sandbox_command", {"command": "true"}
    )
    missing_command = _call_error(
        mcp_client, "execute_sandbox_command", {"name": "e2e-missing-cmd"}
    )
    assert missing_name.strip()
    assert missing_command.strip()


@pytest.mark.integration
def test_MCP_SBX_056_command_runs_inside_requested_sandbox(
    mcp_client, mcp_settings, created_sandbox
):
    name, _ = created_sandbox
    result = _call_ok(
        mcp_client, "execute_sandbox_command", {"name": name, "command": "hostname"}
    )
    sandbox_hostname = result["stdout"].strip()
    server_hostname = _server_hostname(mcp_settings)
    assert sandbox_hostname
    assert sandbox_hostname != server_hostname


@pytest.mark.integration
def test_MCP_SBX_057_command_failure_preserves_diagnostics(mcp_client, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(
        mcp_client,
        "execute_sandbox_command",
        {
            "name": name,
            "command": "printf '%s' 'safe-diagnostic' >&2; exit 9",
        },
    )
    assert "safe-diagnostic" in result["stderr"]
    assert result["return_code"] == 9
