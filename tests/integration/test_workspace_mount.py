from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from .conftest import MCPIntegrationClient


def _sandbox_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _authorize_workspace(host_path: Path) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_mcp_server.cli.workspace_broker",
            "authorize",
            str(host_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        "Workspace authorization failed:\n"
        f"stdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )

    payload = json.loads(result.stdout)

    workspace_id = payload.get("workspace_id")

    assert isinstance(workspace_id, str)
    assert workspace_id.startswith("ws_")

    return workspace_id


def _revoke_workspace(workspace_id: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_mcp_server.cli.workspace_broker",
            "revoke",
            workspace_id,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Workspace revocation failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


@pytest.mark.integration
def test_host_backed_workspace_round_trip(
    mcp_client: MCPIntegrationClient,
    tmp_path: Path,
) -> None:
    if os.environ.get("RUN_WORKSPACE_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_WORKSPACE_INTEGRATION=1 to run workspace integration tests."
        )

    workspace_id = _authorize_workspace(tmp_path)
    sandbox_name = _sandbox_name("host")
    relative_path = f".integration-host-{uuid.uuid4().hex}.txt"

    created = False

    try:
        created_payload = mcp_client.call_tool(
            "create_sandbox",
            {
                "name": sandbox_name,
                "host_workspace_id": workspace_id,
                "profile": "default",
            },
        )

        assert isinstance(created_payload, dict)

        created = True

        assert created_payload["profile"] == "default"
        assert created_payload["host_workspace_id"] == workspace_id

        workspace = created_payload["workspace"]

        assert isinstance(workspace, dict)
        assert workspace == {
            "type": "host",
            "id": workspace_id,
            "authorized": True,
            "root": "/workspace/project",
            "read_only": False,
        }

        mcp_client.call_tool(
            "create_workspace_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": relative_path,
                "content": "written-by-sandbox",
            },
        )

        host_file = tmp_path / relative_path

        assert host_file.read_text(encoding="utf-8") == "written-by-sandbox"

        host_file.write_text(
            "written-by-host",
            encoding="utf-8",
        )

        content = mcp_client.call_tool(
            "read_workspace_text_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": relative_path,
            },
        )

        assert content == "written-by-host"

        mcp_client.call_tool(
            "write_workspace_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": relative_path,
                "content": "rewritten-by-sandbox",
            },
        )

        assert host_file.read_text(encoding="utf-8") == "rewritten-by-sandbox"

        mcp_client.call_tool(
            "delete_workspace_file",
            {
                "sandbox_name": sandbox_name,
                "relative_path": relative_path,
            },
        )

        assert not host_file.exists()

    finally:
        if created:
            mcp_client.call_tool(
                "delete_sandbox",
                {"name": sandbox_name},
            )

        _revoke_workspace(workspace_id)
