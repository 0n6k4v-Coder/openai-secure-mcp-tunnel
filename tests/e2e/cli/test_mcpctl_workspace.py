from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMAND_TIMEOUT_SECONDS = 30

# Keep path validation and grant persistence real; replace only operations that
# would invoke privileged ACL-helper or Docker infrastructure.
SITE_CUSTOMIZE_SOURCE = r"""
import importlib
import json
import os
from pathlib import Path

broker = importlib.import_module("local_mcp_server.cli.workspace_broker")
event_file = Path(os.environ["MCPCTL_E2E_WORKSPACE_EVENTS"])
mode = os.environ.get("MCPCTL_E2E_WORKSPACE_MODE", "normal")

def record(operation, **values):
    event = {"operation": operation, **values}
    with event_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")

def run_acl_helper(host_path, *, operation, host_uid=None, host_gid=None):
    record(
        operation,
        host_path=str(host_path),
        host_uid=host_uid,
        host_gid=host_gid,
    )
    if mode == "acl-failure":
        raise RuntimeError("synthetic ACL helper failure")

def create_volume(volume_name, host_path):
    record("create-volume", volume_name=volume_name, host_path=str(host_path))
    if mode == "volume-failure":
        raise RuntimeError("synthetic volume creation failure")

def remove_volume(volume_name):
    record("remove-volume", volume_name=volume_name)
    if mode == "remove-volume-failure":
        raise RuntimeError("synthetic volume removal failure")

broker._run_acl_helper = run_acl_helper
broker._create_host_backed_volume = create_volume
broker._remove_volume = remove_volume
"""


@pytest.fixture(scope="session")
def mcpctl_executable() -> str:
    configured_path = os.environ.get("MCPCTL_BIN")
    if configured_path:
        candidate = shutil.which(configured_path)
        if candidate is None:
            path = Path(configured_path).expanduser()
            if path.is_file():
                candidate = str(path.resolve())
    else:
        candidate = shutil.which("mcpctl")

    if candidate is None:
        pytest.fail(
            "The installed mcpctl entrypoint was not found. "
            "Run uv sync --locked --all-groups before running CLI E2E tests."
        )

    return str(Path(candidate).resolve())


@pytest.fixture
def workspace_e2e_environment(tmp_path: Path) -> dict[str, str]:
    shim_dir = tmp_path / "python-shim"
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(
        SITE_CUSTOMIZE_SOURCE,
        encoding="utf-8",
    )

    grants_dir = tmp_path / "private-workspace-grants"
    grants_dir.mkdir(mode=0o700)
    grants_dir.chmod(0o700)
    events_file = tmp_path / "workspace-events.jsonl"

    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [
            str(shim_dir),
            str(PROJECT_ROOT / "src"),
            *([environment["PYTHONPATH"]] if environment.get("PYTHONPATH") else []),
        ]
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["NO_COLOR"] = "1"
    environment["WORKSPACE_GRANTS_FILE"] = str(grants_dir / "grants.json")
    environment["WORKSPACE_GRANTS_READ_ONLY"] = "false"
    environment["MCPCTL_E2E_WORKSPACE_EVENTS"] = str(events_file)
    environment["MCPCTL_E2E_WORKSPACE_MODE"] = "normal"
    environment["HOME"] = str(tmp_path / "home")
    Path(environment["HOME"]).mkdir()
    environment["XDG_CONFIG_HOME"] = str(tmp_path / "xdg-config")
    environment["XDG_STATE_HOME"] = str(tmp_path / "xdg-state")
    for key in ("XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        Path(environment[key]).mkdir()

    return environment


def _run(
    executable: str,
    arguments: list[str],
    environment: dict[str, str],
    *,
    mode: str = "normal",
) -> subprocess.CompletedProcess[str]:
    child_environment = environment.copy()
    child_environment["MCPCTL_E2E_WORKSPACE_MODE"] = mode
    return subprocess.run(
        [executable, *arguments],
        cwd=PROJECT_ROOT,
        env=child_environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


def _events(environment: dict[str, str]) -> list[dict[str, Any]]:
    path = Path(environment["MCPCTL_E2E_WORKSPACE_EVENTS"])
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _grant_file(environment: dict[str, str]) -> Path:
    return Path(environment["WORKSPACE_GRANTS_FILE"])


def _json_stdout(result: subprocess.CompletedProcess[str]) -> Any:
    assert result.returncode == 0, (
        f"Command failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stderr == ""
    return json.loads(result.stdout)


def _authorize(
    executable: str,
    environment: dict[str, str],
    host_path: Path,
) -> dict[str, Any]:
    return _json_stdout(
        _run(executable, ["workspace", "authorize", str(host_path)], environment)
    )


def test_cli_ws_001_authorize_returns_workspace_details(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str], tmp_path: Path
) -> None:
    host_path = tmp_path / "host-workspace"
    host_path.mkdir()
    result = _authorize(mcpctl_executable, workspace_e2e_environment, host_path)

    assert re.fullmatch(r"ws_[0-9a-f]{32}", result["workspace_id"])
    assert result["host_path"] == str(host_path.resolve())
    assert result["volume_name"] == f"mcp-ws-{result['workspace_id'][3:]}"
    assert result["target"] == "/workspace/project"
    assert result["read_only"] is False
    assert result["host_uid"] == os.getuid()
    assert result["host_gid"] == os.getgid()
    assert [event["operation"] for event in _events(workspace_e2e_environment)] == [
        "provision-sandbox-acl",
        "create-volume",
    ]


def test_cli_ws_002_authorize_requires_host_path(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable, ["workspace", "authorize"], workspace_e2e_environment
    )
    assert result.returncode == 2
    assert "the following arguments are required: host_path" in result.stderr
    assert result.stdout == ""


def test_cli_ws_003_nonexistent_host_path_does_not_create_grant(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str], tmp_path: Path
) -> None:
    result = _run(
        mcpctl_executable,
        ["workspace", "authorize", str(tmp_path / "does-not-exist")],
        workspace_e2e_environment,
    )
    assert result.returncode == 2
    assert "host_path does not exist" in result.stderr
    assert not _grant_file(workspace_e2e_environment).exists()
    assert _events(workspace_e2e_environment) == []


def test_cli_ws_004_filesystem_root_is_rejected_without_side_effects(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable, ["workspace", "authorize", "/"], workspace_e2e_environment
    )
    assert result.returncode == 2
    assert "filesystem root is not allowed" in result.stderr.lower()
    assert not _grant_file(workspace_e2e_environment).exists()
    assert _events(workspace_e2e_environment) == []


def test_cli_ws_005_authorize_help(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["workspace", "authorize", "--help"],
        workspace_e2e_environment,
    )
    assert result.returncode == 0
    assert "usage: mcpctl workspace authorize" in result.stdout
    assert "host_path" in result.stdout


def test_cli_ws_006_list_includes_authorized_grant(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str], tmp_path: Path
) -> None:
    host_path = tmp_path / "listed-workspace"
    host_path.mkdir()
    grant = _authorize(mcpctl_executable, workspace_e2e_environment, host_path)
    result = _run(mcpctl_executable, ["workspace", "list"], workspace_e2e_environment)
    grants = _json_stdout(result)
    assert grant["workspace_id"] in {item["workspace_id"] for item in grants}


def test_cli_ws_007_list_json_returns_valid_json(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str], tmp_path: Path
) -> None:
    host_path = tmp_path / "json-workspace"
    host_path.mkdir()
    grant = _authorize(mcpctl_executable, workspace_e2e_environment, host_path)
    result = _run(
        mcpctl_executable, ["workspace", "list", "--json"], workspace_e2e_environment
    )
    grants = _json_stdout(result)
    assert any(item["workspace_id"] == grant["workspace_id"] for item in grants)


def test_cli_ws_008_list_help_documents_json_option(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable, ["workspace", "list", "--help"], workspace_e2e_environment
    )
    assert result.returncode == 0
    assert "usage: mcpctl workspace list" in result.stdout
    assert "--json" in result.stdout


def test_cli_ws_009_revoke_removes_existing_grant(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str], tmp_path: Path
) -> None:
    host_path = tmp_path / "revoke-workspace"
    host_path.mkdir()
    grant = _authorize(mcpctl_executable, workspace_e2e_environment, host_path)
    result = _run(
        mcpctl_executable,
        ["workspace", "revoke", grant["workspace_id"]],
        workspace_e2e_environment,
    )
    revoked = _json_stdout(result)
    assert revoked["workspace_id"] == grant["workspace_id"]
    assert revoked["revoked"] is True
    grants = json.loads(
        _grant_file(workspace_e2e_environment).read_text(encoding="utf-8")
    )
    assert grant["workspace_id"] not in grants
    assert [event["operation"] for event in _events(workspace_e2e_environment)] == [
        "provision-sandbox-acl",
        "create-volume",
        "remove-sandbox-acl",
        "remove-volume",
    ]


def test_cli_ws_010_revoke_requires_workspace_id(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(mcpctl_executable, ["workspace", "revoke"], workspace_e2e_environment)
    assert result.returncode == 2
    assert "the following arguments are required: workspace_id" in result.stderr
    assert result.stdout == ""


def test_cli_ws_011_revoke_unknown_id_reports_failure(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["workspace", "revoke", "ws_00000000000000000000000000000000"],
        workspace_e2e_environment,
    )
    assert result.returncode == 2
    assert "was not found" in result.stderr
    assert result.stdout == ""


def test_cli_ws_012_revoke_help(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable, ["workspace", "revoke", "--help"], workspace_e2e_environment
    )
    assert result.returncode == 0
    assert "usage: mcpctl workspace revoke" in result.stdout
    assert "workspace_id" in result.stdout


def test_cli_ws_013_authorize_list_revoke_list_round_trip(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str], tmp_path: Path
) -> None:
    host_path = tmp_path / "round-trip-workspace"
    host_path.mkdir()
    grant = _authorize(mcpctl_executable, workspace_e2e_environment, host_path)
    before = _json_stdout(
        _run(mcpctl_executable, ["workspace", "list"], workspace_e2e_environment)
    )
    assert any(item["workspace_id"] == grant["workspace_id"] for item in before)
    _json_stdout(
        _run(
            mcpctl_executable,
            ["workspace", "revoke", grant["workspace_id"]],
            workspace_e2e_environment,
        )
    )
    after = _json_stdout(
        _run(mcpctl_executable, ["workspace", "list"], workspace_e2e_environment)
    )
    assert all(item["workspace_id"] != grant["workspace_id"] for item in after)


def test_cli_ws_014_workspace_help_lists_subcommands(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(mcpctl_executable, ["workspace", "--help"], workspace_e2e_environment)
    assert result.returncode == 0
    for command in ("authorize", "revoke", "list"):
        assert command in result.stdout


def test_cli_ws_015_unknown_workspace_subcommand_is_rejected(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["workspace", "unknown-subcommand"],
        workspace_e2e_environment,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert result.stdout == ""


def test_cli_ws_016_authorize_list_revoke_json_output_contract(
    mcpctl_executable: str, workspace_e2e_environment: dict[str, str], tmp_path: Path
) -> None:
    host_path = tmp_path / "json-contract-workspace"
    host_path.mkdir()
    grant = _authorize(mcpctl_executable, workspace_e2e_environment, host_path)
    listed = _json_stdout(
        _run(
            mcpctl_executable,
            ["workspace", "list", "--json"],
            workspace_e2e_environment,
        )
    )
    assert any(item["workspace_id"] == grant["workspace_id"] for item in listed)
    revoked = _json_stdout(
        _run(
            mcpctl_executable,
            ["workspace", "revoke", grant["workspace_id"]],
            workspace_e2e_environment,
        )
    )
    assert revoked["revoked"] is True
    assert revoked["workspace_id"] == grant["workspace_id"]
