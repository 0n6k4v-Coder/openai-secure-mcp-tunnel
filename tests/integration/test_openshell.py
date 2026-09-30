from __future__ import annotations

import os
import shutil
import subprocess

import pytest


@pytest.mark.integration
def test_openshell_gateway_is_reachable() -> None:
    if os.environ.get(
        "RUN_OPENSHELL_INTEGRATION"
    ) != "1":
        pytest.skip(
            "Set RUN_OPENSHELL_INTEGRATION=1 to run OpenShell integration tests."
        )

    if shutil.which("openshell") is None:
        pytest.fail(
            "OpenShell CLI is required for this integration test."
        )

    result = subprocess.run(
        [
            "openshell",
            "sandbox",
            "list",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        "OpenShell sandbox list failed: "
        f"{result.stderr.strip()}"
    )