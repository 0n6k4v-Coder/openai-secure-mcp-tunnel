from __future__ import annotations

from typing import Any

import pytest

from .conftest import _call_error, _call_ok


@pytest.mark.integration
def test_MCP_SBX_020_status_for_existing_sandbox(mcp_client: Any, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(mcp_client, "sandbox_status", {"name": name})
    assert isinstance(result, dict)
    assert result["name"] == name


@pytest.mark.integration
def test_MCP_SBX_021_status_for_missing_sandbox(
    mcp_client: Any, missing_sandbox_name: str
):
    diagnostic = _call_error(
        mcp_client, "sandbox_status", {"name": missing_sandbox_name}
    )
    assert "not found" in diagnostic.lower()


@pytest.mark.integration
def test_MCP_SBX_022_status_response_contains_expected_metadata(
    mcp_client: Any, created_sandbox
):
    name, _ = created_sandbox
    result = _call_ok(mcp_client, "sandbox_status", {"name": name})
    assert isinstance(result, dict)
    assert result["name"] == name
    assert "phase" in result
    assert "status" in result
    assert result["profile"] == "default"
    assert result["workspace"]["type"] == "sandbox"


@pytest.mark.integration
def test_MCP_SBX_023_logs_with_default_since_duration(mcp_client: Any, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(mcp_client, "sandbox_logs", {"name": name})
    assert isinstance(result, str)


@pytest.mark.integration
def test_MCP_SBX_024_logs_with_explicit_supported_durations(
    mcp_client: Any, created_sandbox
):
    name, _ = created_sandbox
    for duration in ("1h", "30s"):
        result = _call_ok(mcp_client, "sandbox_logs", {"name": name, "since": duration})
        assert isinstance(result, str)


@pytest.mark.integration
def test_MCP_SBX_025_logs_for_missing_sandbox_fail(
    mcp_client: Any, missing_sandbox_name: str
):
    diagnostic = _call_error(
        mcp_client,
        "sandbox_logs",
        {"name": missing_sandbox_name, "since": "5m"},
    )
    assert diagnostic.strip()


@pytest.mark.integration
def test_MCP_SBX_026_logs_reject_empty_duration(mcp_client: Any, created_sandbox):
    name, _ = created_sandbox
    diagnostic = _call_error(mcp_client, "sandbox_logs", {"name": name, "since": ""})
    assert diagnostic.strip()


@pytest.mark.integration
def test_MCP_SBX_027_logs_preserve_output_as_text(mcp_client: Any, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(mcp_client, "sandbox_logs", {"name": name, "since": "30s"})
    assert isinstance(result, str)
