from __future__ import annotations

import uuid
from typing import Any

import pytest

from .conftest import _call_error, _call_ok, _invoke


@pytest.mark.integration
def test_MCP_SBX_001_create_valid_sandbox_with_default_profile(sandbox_factory):
    name, result = sandbox_factory()
    assert result["name"] == name
    assert result["profile"] == "default"


@pytest.mark.integration
def test_MCP_SBX_002_create_sandbox_using_default_profile(sandbox_factory):
    name, result = sandbox_factory(profile="default")
    assert result["name"] == name
    assert result["profile"] == "default"


@pytest.mark.integration
def test_MCP_SBX_003_create_sandbox_using_browser_profile(
    sandbox_factory, browser_profile_enabled
):
    name, result = sandbox_factory(profile="browser")
    assert result["name"] == name
    assert result["profile"] == "browser"


@pytest.mark.integration
def test_MCP_SBX_004_create_standalone_sandbox_without_host_workspace(
    sandbox_factory,
):
    name, result = sandbox_factory()
    assert result["name"] == name
    assert "host_workspace_id" not in result
    assert result["workspace"]["type"] == "sandbox"


@pytest.mark.integration
def test_MCP_SBX_005_create_sandbox_with_authorized_host_workspace(
    sandbox_factory, host_workspace_id: str
):
    name, result = sandbox_factory(host_workspace_id=host_workspace_id)
    assert result["name"] == name
    assert result["host_workspace_id"] == host_workspace_id
    assert result["host_workspace"]["authorized"] is True


@pytest.mark.integration
def test_MCP_SBX_006_reject_unknown_host_workspace(mcp_client: Any):
    diagnostic = _call_error(
        mcp_client,
        "create_sandbox",
        {
            "name": f"e2e-unknown-{uuid.uuid4().hex[:6]}",
            "host_workspace_id": f"unknown-e2e-{uuid.uuid4().hex[:6]}",
        },
    )
    assert diagnostic.strip()


@pytest.mark.integration
def test_MCP_SBX_007_reject_unsupported_profile(mcp_client: Any):
    diagnostic = _call_error(
        mcp_client,
        "create_sandbox",
        {"name": f"e2e-profile-{uuid.uuid4().hex[:6]}", "profile": "unsupported"},
    )
    assert diagnostic.strip()


@pytest.mark.integration
def test_MCP_SBX_008_reject_missing_or_invalid_name(mcp_client: Any):
    missing_name_result = _invoke(mcp_client, "create_sandbox", {"profile": "default"})
    assert missing_name_result.is_error

    invalid_name_diagnostic = _call_error(
        mcp_client,
        "create_sandbox",
        {"name": "", "profile": "default"},
    )
    assert invalid_name_diagnostic.strip()


@pytest.mark.integration
def test_MCP_SBX_009_reject_duplicate_sandbox_name(mcp_client: Any, sandbox_factory):
    name, _ = sandbox_factory()
    diagnostic = _call_error(
        mcp_client, "create_sandbox", {"name": name, "profile": "default"}
    )
    assert diagnostic.strip()


@pytest.mark.integration
def test_MCP_SBX_010_list_sandboxes_returns_json_list(mcp_client: Any):
    result = _call_ok(mcp_client, "list_sandboxes")
    assert isinstance(result, list)
    assert all(isinstance(item, dict) for item in result)


@pytest.mark.integration
def test_MCP_SBX_011_list_sandboxes_in_empty_test_workspace(
    mcp_client: Any, empty_workspace_assertion_enabled
):
    result = _call_ok(mcp_client, "list_sandboxes")
    assert result == []


@pytest.mark.integration
def test_MCP_SBX_012_created_sandbox_appears_in_list(mcp_client: Any, sandbox_factory):
    name, _ = sandbox_factory()
    result = _call_ok(mcp_client, "list_sandboxes")
    assert any(item.get("name") == name for item in result)


@pytest.mark.integration
def test_MCP_SBX_013_invalid_create_does_not_report_success(mcp_client: Any):
    name = f"e2e-invalid-{uuid.uuid4().hex[:6]}"
    _call_error(
        mcp_client,
        "create_sandbox",
        {"name": name, "profile": "not-a-profile"},
    )
    sandboxes = _call_ok(mcp_client, "list_sandboxes")
    assert all(item.get("name") != name for item in sandboxes)
