from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMAND_TIMEOUT_SECONDS = 30

SITE_CUSTOMIZE_SOURCE = r"""
import importlib
import os
from types import SimpleNamespace


_sandbox_adapter = importlib.import_module(
    "local_mcp_server.infrastructure.openshell.sandbox"
)
_cli_main = importlib.import_module("local_mcp_server.cli.main")


def _sandbox_record(name, sandbox_id):
    return SimpleNamespace(
        id=sandbox_id,
        name=name,
        phase="Ready",
        status=SimpleNamespace(phase="Ready"),
        labels={
            _sandbox_adapter.SANDBOX_PROFILE_LABEL: "default",
        },
    )


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def list_all(self, *, workspace):
        if workspace != _sandbox_adapter.OPENSHELL_WORKSPACE:
            raise AssertionError(
                f"Unexpected OpenShell workspace: {workspace!r}"
            )

        if os.environ.get("MCPCTL_E2E_FIXTURE_MODE") == "missing-status":
            return []

        return [
            _sandbox_record(
                "e2e-list-fixture",
                "sandbox-id-list-fixture",
            ),
            _sandbox_record(
                "e2e-status-fixture",
                "sandbox-id-status-fixture",
            ),
        ]


_sandbox_adapter._client = lambda: _FakeClient()

if os.environ.get("MCPCTL_E2E_FIXTURE_MODE") == "malformed-status":
    _cli_main.sandbox_status = lambda _name: "{not valid JSON"
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
            "Run uv sync before running CLI E2E tests."
        )

    return str(Path(candidate).resolve())


@pytest.fixture
def sandbox_cli_environment(tmp_path: Path) -> dict[str, str]:
    shim_dir = tmp_path / "python-startup"
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(
        SITE_CUSTOMIZE_SOURCE,
        encoding="utf-8",
    )

    config_home = tmp_path / "xdg-config"
    state_home = tmp_path / "xdg-state"
    mcp_config_dir = tmp_path / "mcp-config"
    mcp_state_dir = tmp_path / "mcp-state"
    workspace_grants_dir = tmp_path / "workspace-grants"

    for directory in (
        config_home,
        state_home,
        mcp_config_dir,
        mcp_state_dir,
        workspace_grants_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

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
    environment["XDG_CONFIG_HOME"] = str(config_home)
    environment["XDG_STATE_HOME"] = str(state_home)
    environment["MCP_CONFIG_DIR"] = str(mcp_config_dir)
    environment["MCP_STATE_DIR"] = str(mcp_state_dir)
    environment["WORKSPACE_GRANTS_DIR"] = str(workspace_grants_dir)

    # Ensure a failed test shim cannot fall back to the user's gateway config.
    environment.pop("OPENSHELL_GATEWAY", None)
    environment.pop("OPENSHELL_GATEWAY_ENDPOINT", None)
    environment.pop("OPENSHELL_GATEWAY_INSECURE", None)
    environment["MCPCTL_E2E_FIXTURE_MODE"] = "normal"

    return environment


def _run_mcpctl(
    executable: str,
    arguments: list[str],
    environment: dict[str, str],
    *,
    fixture_mode: str = "normal",
) -> subprocess.CompletedProcess[str]:
    child_environment = environment.copy()
    child_environment["MCPCTL_E2E_FIXTURE_MODE"] = fixture_mode

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


def test_cli_sbx_020_list_delegates_and_displays_collection(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "list"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox list failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "NAME" in result.stdout
    assert "STATUS" in result.stdout
    assert "PROFILE" in result.stdout
    assert "HOST WORKSPACE ID" in result.stdout
    assert "ID" in result.stdout
    assert "e2e-list-fixture" in result.stdout
    assert "e2e-status-fixture" in result.stdout
    assert "Ready" in result.stdout


def test_cli_sbx_021_list_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "list", "--help"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0
    assert "usage: mcpctl sandbox list" in result.stdout
    assert "-h, --help" in result.stdout
    assert "--json" not in result.stdout


def test_cli_sbx_022_list_rejects_json(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "list", "--json"],
        sandbox_cli_environment,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --json" in result.stderr
    assert result.stdout == ""


def test_cli_sbx_023_status_displays_named_sandbox(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "status", "e2e-status-fixture"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox status failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Name:                e2e-status-fixture" in result.stdout
    assert "Status:              Ready" in result.stdout
    assert "Profile:             default" in result.stdout
    assert "ID:                  sandbox-id-status-fixture" in result.stdout


def test_cli_sbx_024_status_json_returns_valid_object(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "status", "e2e-status-fixture", "--json"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox status JSON failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert payload["name"] == "e2e-status-fixture"
    assert payload["status"] == "Ready"
    assert payload["profile"] == "default"


def test_cli_sbx_025_missing_sandbox_returns_clear_failure(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "status", "e2e-missing"],
        sandbox_cli_environment,
        fixture_mode="missing-status",
    )

    assert result.returncode == 2
    assert "ERROR: Sandbox 'e2e-missing' was not found." in result.stderr
    assert result.stdout == ""


def test_cli_sbx_026_status_requires_name(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "status"],
        sandbox_cli_environment,
    )

    assert result.returncode == 2
    assert "the following arguments are required: name" in result.stderr


def test_cli_sbx_027_status_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "status", "--help"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0
    assert "usage: mcpctl sandbox status" in result.stdout
    assert "name" in result.stdout
    assert "--json" in result.stdout


def test_cli_sbx_028_status_json_schema(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "status", "e2e-status-fixture", "--json"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox status JSON failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)

    for field in (
        "id",
        "name",
        "openshell_workspace",
        "phase",
        "status",
        "profile",
    ):
        assert isinstance(payload.get(field), str), (
            f"Expected {field!r} to be a string."
        )

    assert isinstance(payload.get("workspace"), dict)
    assert isinstance(payload.get("labels"), dict)

    workspace = payload["workspace"]
    assert workspace.get("type") == "sandbox"
    assert workspace.get("id") == "e2e-status-fixture"
    assert workspace.get("authorized") is True
    assert isinstance(workspace.get("root"), str)
    assert isinstance(workspace.get("read_only"), bool)

    assert payload["name"] == "e2e-status-fixture"
    assert payload["status"] == "Ready"
    assert payload["profile"] == "default"
    assert "host_workspace_id" not in payload


def test_cli_sbx_029_status_rejects_malformed_downstream_json(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "status", "e2e-status-fixture", "--json"],
        sandbox_cli_environment,
        fixture_mode="malformed-status",
    )

    assert result.returncode == 2
    assert "ERROR: OpenShell returned invalid JSON." in result.stderr
    assert result.stdout == ""
