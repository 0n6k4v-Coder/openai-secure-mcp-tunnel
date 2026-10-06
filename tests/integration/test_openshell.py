from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
import uuid

import pytest

from .conftest import MCPIntegrationClient


def _sandbox_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _sandbox_payload(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _assert_standalone_workspace(
    payload: dict[str, object],
    sandbox_name: str,
) -> None:
    assert payload["name"] == sandbox_name
    assert payload["profile"] == "default"
    assert "host_workspace_id" not in payload

    workspace = payload["workspace"]

    assert isinstance(workspace, dict)
    assert workspace == {
        "type": "sandbox",
        "id": sandbox_name,
        "authorized": True,
        "root": "/workspace/project",
        "read_only": False,
    }


@pytest.mark.integration
def test_openshell_gateway_health() -> None:
    if os.environ.get("RUN_OPENSHELL_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_OPENSHELL_INTEGRATION=1 to run OpenShell integration tests."
        )

    url = os.environ.get(
        "OPENSHELL_HEALTH_URL",
        "http://127.0.0.1:8081/healthz",
    )

    request = urllib.request.Request(
        url,
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=5,
        ) as response:
            status = response.status
    except urllib.error.URLError as exc:
        pytest.fail(f"OpenShell Gateway health endpoint is unreachable: {exc}")

    assert status == 200


@pytest.mark.integration
def test_standalone_sandbox_lifecycle_and_workspace(
    mcp_client: MCPIntegrationClient,
) -> None:
    sandbox_name = _sandbox_name("standalone")
    relative_path = f".integration-{uuid.uuid4().hex}.txt"

    created = False

    try:
        created_payload = _sandbox_payload(
            mcp_client.call_tool(
                "create_sandbox",
                {
                    "name": sandbox_name,
                    "profile": "default",
                },
            )
        )

        created = True

        _assert_standalone_workspace(
            created_payload,
            sandbox_name,
        )

        execution = mcp_client.call_tool(
            "execute_sandbox_command",
            {
                "name": sandbox_name,
                "command": ("sh -lc 'id && pwd && printf standalone-integration-ok'"),
            },
        )

        assert "uid=10001" in str(execution)
        assert "/workspace" in str(execution)
        assert "standalone-integration-ok" in str(execution)

        mcp_client.call_tool(
            "create_workspace_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": relative_path,
                "content": "before-recreate",
            },
        )

        content = mcp_client.call_tool(
            "read_workspace_text_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": relative_path,
            },
        )

        assert content == "before-recreate"

        stopped = _sandbox_payload(
            mcp_client.call_tool(
                "stop_sandbox",
                {"name": sandbox_name},
            )
        )

        assert stopped["name"] == sandbox_name

        started = _sandbox_payload(
            mcp_client.call_tool(
                "start_sandbox",
                {"name": sandbox_name},
            )
        )

        assert started["name"] == sandbox_name

        restarted = _sandbox_payload(
            mcp_client.call_tool(
                "restart_sandbox",
                {"name": sandbox_name},
            )
        )

        assert restarted["name"] == sandbox_name

        repaired = _sandbox_payload(
            mcp_client.call_tool(
                "repair_sandbox",
                {"name": sandbox_name},
            )
        )

        assert repaired["name"] == sandbox_name

        recreated = _sandbox_payload(
            mcp_client.call_tool(
                "recreate_sandbox",
                {"name": sandbox_name},
            )
        )

        _assert_standalone_workspace(
            recreated,
            sandbox_name,
        )

        recreated_path = f".recreated-{uuid.uuid4().hex}.txt"
        mcp_client.call_tool(
            "create_workspace_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": recreated_path,
                "content": "after-recreate",
            },
        )

        recreated_content = mcp_client.call_tool(
            "read_workspace_text_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": recreated_path,
            },
        )

        assert recreated_content == "after-recreate"

        status = _sandbox_payload(
            mcp_client.call_tool(
                "sandbox_status",
                {"name": sandbox_name},
            )
        )

        _assert_standalone_workspace(
            status,
            sandbox_name,
        )

    finally:
        if created:
            mcp_client.call_tool(
                "delete_sandbox",
                {"name": sandbox_name},
            )


@pytest.mark.integration
def test_sandbox_name_limit_is_enforced_before_gateway(
    mcp_client: MCPIntegrationClient,
) -> None:
    if os.environ.get("RUN_OPENSHELL_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_OPENSHELL_INTEGRATION=1 to run OpenShell integration tests."
        )

    result = mcp_client.call_tool_expect_error(
        "create_sandbox",
        {
            "name": "a" * 20,
            "profile": "browser",
        },
    )

    assert result.is_error is True


@pytest.mark.integration
def test_browser_profile_runs_inside_open_shell(
    mcp_client: MCPIntegrationClient,
) -> None:
    if os.environ.get("RUN_BROWSER_INTEGRATION") != "1":
        pytest.skip("Set RUN_BROWSER_INTEGRATION=1 to run browser integration tests.")

    sandbox_name = _sandbox_name("browser")
    created = False

    try:
        created_payload = _sandbox_payload(
            mcp_client.call_tool(
                "create_sandbox",
                {
                    "name": sandbox_name,
                    "profile": "browser",
                },
            )
        )

        created = True

        assert created_payload["profile"] == "browser"

        workspace = created_payload["workspace"]

        assert isinstance(workspace, dict)
        assert workspace["type"] == "sandbox"
        assert workspace["root"] == "/workspace/project"

        deadline = time.monotonic() + 30
        last_error: AssertionError | None = None

        while time.monotonic() < deadline:
            try:
                result = mcp_client.call_tool(
                    "execute_chrome_devtools_command",
                    {
                        "sandbox_name": sandbox_name,
                        "command": "list_pages",
                        "arguments": [],
                    },
                )
                assert result is not None
                break
            except AssertionError as exc:
                last_error = exc
                time.sleep(0.5)
        else:
            assert last_error is None, str(last_error)

        status = _sandbox_payload(
            mcp_client.call_tool(
                "sandbox_status",
                {"name": sandbox_name},
            )
        )
        browser_status = status.get("browser")
        assert isinstance(browser_status, dict)
        devtools_status = browser_status.get("devtools")
        assert isinstance(devtools_status, dict)
        assert devtools_status["state"] == "ready"

    finally:
        if created:
            mcp_client.call_tool(
                "delete_sandbox",
                {"name": sandbox_name},
            )
