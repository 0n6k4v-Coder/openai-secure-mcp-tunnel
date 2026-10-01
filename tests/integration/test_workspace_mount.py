from __future__ import annotations

import os
import shutil
import subprocess

import pytest


@pytest.mark.integration
def test_workspace_mount_end_to_end() -> None:
    if os.environ.get("RUN_WORKSPACE_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_WORKSPACE_INTEGRATION=1 to run workspace integration tests."
        )

    if shutil.which("docker") is None:
        pytest.fail("Docker CLI is required for this integration test.")

    if shutil.which("mcp-sandbox") is None:
        pytest.fail("mcp-sandbox CLI is required for this integration test.")

    result = subprocess.run(
        [
            "mcp-sandbox",
            "workspace",
            "list",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Workspace broker integration check failed: {result.stderr.strip()}"
    )
