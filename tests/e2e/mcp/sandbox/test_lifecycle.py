from __future__ import annotations

import os

import pytest

from .conftest import _call_error, _call_ok


@pytest.mark.integration
def test_MCP_SBX_030_start_stopped_sandbox(mcp_client, created_sandbox):
    name, _ = created_sandbox
    _call_ok(mcp_client, "stop_sandbox", {"name": name})
    started = _call_ok(mcp_client, "start_sandbox", {"name": name})
    assert isinstance(started, dict)
    assert started["name"] == name


@pytest.mark.integration
def test_MCP_SBX_031_start_missing_sandbox_fails(mcp_client, missing_sandbox_name):
    assert _call_error(
        mcp_client, "start_sandbox", {"name": missing_sandbox_name}
    ).strip()


@pytest.mark.integration
def test_MCP_SBX_032_stop_running_sandbox_retains_resource(mcp_client, created_sandbox):
    name, _ = created_sandbox
    stopped = _call_ok(mcp_client, "stop_sandbox", {"name": name})
    assert isinstance(stopped, dict)
    assert stopped["name"] == name
    status = _call_ok(mcp_client, "sandbox_status", {"name": name})
    assert status["name"] == name


@pytest.mark.integration
def test_MCP_SBX_033_stop_missing_sandbox_fails(mcp_client, missing_sandbox_name):
    assert _call_error(
        mcp_client, "stop_sandbox", {"name": missing_sandbox_name}
    ).strip()


@pytest.mark.integration
def test_MCP_SBX_034_restart_existing_sandbox(mcp_client, created_sandbox):
    name, _ = created_sandbox
    result = _call_ok(mcp_client, "restart_sandbox", {"name": name})
    assert isinstance(result, dict)
    assert result["name"] == name


@pytest.mark.integration
def test_MCP_SBX_035_restart_missing_sandbox_fails(mcp_client, missing_sandbox_name):
    assert _call_error(
        mcp_client, "restart_sandbox", {"name": missing_sandbox_name}
    ).strip()


@pytest.mark.integration
def test_MCP_SBX_036_repair_stopped_sandbox(mcp_client, created_sandbox):
    name, _ = created_sandbox
    _call_ok(mcp_client, "stop_sandbox", {"name": name})
    repaired = _call_ok(mcp_client, "repair_sandbox", {"name": name})
    assert isinstance(repaired, dict)
    assert repaired["name"] == name


@pytest.mark.integration
def test_MCP_SBX_037_repair_unrecoverable_sandbox_requires_fault_injection():
    if os.environ.get("MCP_SBX_E2E_FAULT_INJECTION") != "1":
        pytest.skip(
            "BLOCKED: no deterministic fault-injection fixture exists for an "
            "existing unrecoverable sandbox; a missing-sandbox case is not equivalent."
        )
    pytest.skip(
        "BLOCKED: a reviewed fault-injection implementation must be added to "
        "the dedicated runtime before this scenario can run."
    )


@pytest.mark.integration
def test_MCP_SBX_038_recreate_host_backed_sandbox_preserves_binding(
    mcp_client, sandbox_factory, host_workspace_id: str
):
    name, _ = sandbox_factory(host_workspace_id=host_workspace_id)
    result = _call_ok(mcp_client, "recreate_sandbox", {"name": name})
    assert isinstance(result, dict)
    assert result["name"] == name
    assert result["profile"] == "default"
    assert result["host_workspace_id"] == host_workspace_id


@pytest.mark.integration
def test_MCP_SBX_039_recreate_standalone_sandbox_preserves_mode(
    mcp_client, created_sandbox
):
    name, _ = created_sandbox
    result = _call_ok(mcp_client, "recreate_sandbox", {"name": name})
    assert isinstance(result, dict)
    assert result["name"] == name
    assert result["profile"] == "default"
    assert "host_workspace_id" not in result
    assert result["workspace"]["type"] == "sandbox"


@pytest.mark.integration
def test_MCP_SBX_040_recreate_missing_sandbox_fails(mcp_client, missing_sandbox_name):
    assert _call_error(
        mcp_client, "recreate_sandbox", {"name": missing_sandbox_name}
    ).strip()


@pytest.mark.integration
def test_MCP_SBX_041_delete_existing_test_sandbox(mcp_client, sandbox_factory):
    name, _ = sandbox_factory()
    result = _call_ok(mcp_client, "delete_sandbox", {"name": name})
    assert isinstance(result, dict)
    assert result["name"] == name
    assert result["deleted"] is True


@pytest.mark.integration
def test_MCP_SBX_042_delete_missing_sandbox_fails(mcp_client, missing_sandbox_name):
    assert _call_error(
        mcp_client, "delete_sandbox", {"name": missing_sandbox_name}
    ).strip()


@pytest.mark.integration
def test_MCP_SBX_043_deleted_sandbox_is_absent(mcp_client, sandbox_factory):
    name, _ = sandbox_factory()
    _call_ok(mcp_client, "delete_sandbox", {"name": name})
    diagnostic = _call_error(mcp_client, "sandbox_status", {"name": name})
    assert "not found" in diagnostic.lower()
    sandboxes = _call_ok(mcp_client, "list_sandboxes")
    assert all(item.get("name") != name for item in sandboxes)


@pytest.mark.integration
def test_MCP_SBX_044_lifecycle_failure_does_not_break_service(
    mcp_client, missing_sandbox_name
):
    assert _call_error(
        mcp_client, "restart_sandbox", {"name": missing_sandbox_name}
    ).strip()
    result = _call_ok(mcp_client, "list_sandboxes")
    assert isinstance(result, list)


@pytest.mark.integration
def test_MCP_SBX_045_lifecycle_operations_are_sandbox_scoped(
    mcp_client, sandbox_factory
):
    first_name, _ = sandbox_factory()
    second_name, _ = sandbox_factory()
    _call_ok(mcp_client, "stop_sandbox", {"name": first_name})
    first_status = _call_ok(mcp_client, "sandbox_status", {"name": first_name})
    second_status = _call_ok(mcp_client, "sandbox_status", {"name": second_name})
    assert first_status["name"] == first_name
    assert second_status["name"] == second_name


@pytest.mark.integration
def test_MCP_SBX_046_cleanup_after_failed_lifecycle_operation(
    mcp_client, sandbox_factory, missing_sandbox_name
):
    name, _ = sandbox_factory()
    assert _call_error(
        mcp_client, "restart_sandbox", {"name": missing_sandbox_name}
    ).strip()
    assert _call_ok(mcp_client, "sandbox_status", {"name": name})["name"] == name
    _call_ok(mcp_client, "delete_sandbox", {"name": name})
    diagnostic = _call_error(mcp_client, "sandbox_status", {"name": name})
    assert "not found" in diagnostic.lower()
