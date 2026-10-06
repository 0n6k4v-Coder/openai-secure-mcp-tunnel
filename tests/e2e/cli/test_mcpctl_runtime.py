from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_mcpctl_runtime_command_is_available_in_help(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "local_mcp_server.cli.mcpctl", "runtime", "list", "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]["name"] == "default"
