from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMAND_TIMEOUT_SECONDS = 30

# The installed CLI is exercised in a subprocess. sitecustomize substitutes only
# the two infrastructure service calls, so tests never mutate a real sandbox.
SITE_CUSTOMIZE_SOURCE = r"""import json
import os
from pathlib import Path

import importlib

cli = importlib.import_module("local_mcp_server.cli.main")

record_file = Path(os.environ["MCPCTL_E2E_SERVICE_CALLS"])
mode = os.environ.get("MCPCTL_E2E_SERVICE_MODE", "success")

def record(operation, name):
    with record_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"operation": operation, "name": name}) + "\n")

def delete_sandbox(name):
    record("delete", name)
    if mode == "delete-missing":
        raise cli.SandboxError(f"Sandbox not found: {name}")
    if mode == "delete-failure":
        raise cli.SandboxError("Sandbox deletion failed: synthetic failure")
    return json.dumps({"name": name, "deleted": True})

def recreate_sandbox(name):
    record("recreate", name)
    if mode == "recreate-missing":
        raise cli.SandboxError(f"Sandbox not found: {name}")
    if mode == "recreate-failure":
        raise cli.SandboxError("Sandbox recreation failed: synthetic failure")
    if mode == "invalid-json":
        return "{not valid json"
    if mode == "standalone":
        return json.dumps({"name": name, "status": "running", "profile": "browser"})
    if mode == "host":
        return json.dumps({"name": name, "status": "running", "profile": "browser", "host_workspace_id": "workspace-e2e-fixture"})
    return json.dumps({"name": name, "status": "running", "profile": "default"})

cli.delete_sandbox = delete_sandbox
cli.recreate_sandbox = recreate_sandbox
"""


@pytest.fixture(scope="session")
def mcpctl_executable() -> str:
    configured_path = os.environ.get("MCPCTL_BIN")
    if configured_path:
        candidate = shutil.which(configured_path)
        if candidate is None and Path(configured_path).expanduser().is_file():
            candidate = str(Path(configured_path).expanduser().resolve())
    else:
        candidate = shutil.which("mcpctl")
    if candidate is None:
        pytest.fail(
            "The installed mcpctl entrypoint was not found. "
            "Run uv sync --locked --all-groups before running CLI E2E tests."
        )
    return str(Path(candidate).resolve())


@pytest.fixture
def delete_recreate_environment(tmp_path: Path) -> dict[str, str]:
    shim_dir = tmp_path / "python-shim"
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(SITE_CUSTOMIZE_SOURCE, encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(shim_dir), str(PROJECT_ROOT / "src"), environment.get("PYTHONPATH", "")]
    )
    environment["MCPCTL_E2E_SERVICE_CALLS"] = str(tmp_path / "service-calls.jsonl")
    environment["MCPCTL_E2E_SERVICE_MODE"] = "success"
    environment["XDG_CONFIG_HOME"] = str(tmp_path / "xdg-config")
    environment["XDG_STATE_HOME"] = str(tmp_path / "xdg-state")
    Path(environment["XDG_CONFIG_HOME"]).mkdir(parents=True)
    Path(environment["XDG_STATE_HOME"]).mkdir(parents=True)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["NO_COLOR"] = "1"
    return environment


def _run(
    executable: str,
    arguments: list[str],
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


def _calls(environment: dict[str, str]) -> list[dict[str, str]]:
    path = Path(environment["MCPCTL_E2E_SERVICE_CALLS"])
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_cli_sbx_060_delete_calls_service_and_reports_success(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["sandbox", "delete", "e2e-delete", "--yes"],
        delete_recreate_environment,
    )
    assert result.returncode == 0, result.stderr
    assert "Sandbox deleted: e2e-delete" in result.stdout
    assert _calls(delete_recreate_environment) == [
        {"operation": "delete", "name": "e2e-delete"}
    ]


def test_cli_sbx_061_delete_json_is_valid_and_forwards_flag(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["sandbox", "delete", "e2e-delete-json", "--yes", "--json"],
        delete_recreate_environment,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "name": "e2e-delete-json",
        "deleted": True,
        "package_state": {
            "sandbox": "e2e-delete-json",
            "package_state": "NONE",
            "removed": False,
        },
    }
    assert _calls(delete_recreate_environment) == [
        {"operation": "delete", "name": "e2e-delete-json"}
    ]


def test_cli_sbx_062_delete_help_lists_json_option(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable, ["sandbox", "delete", "--help"], delete_recreate_environment
    )
    assert result.returncode == 0
    assert "usage: mcpctl sandbox delete" in result.stdout
    assert "--json" in result.stdout
    assert _calls(delete_recreate_environment) == []


def test_cli_sbx_063_delete_missing_reports_failure(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    delete_recreate_environment["MCPCTL_E2E_SERVICE_MODE"] = "delete-missing"
    result = _run(
        mcpctl_executable,
        ["sandbox", "delete", "e2e-missing", "--yes"],
        delete_recreate_environment,
    )
    assert result.returncode != 0
    assert "e2e-missing" in result.stderr
    assert "not found" in result.stderr.lower()
    assert "Sandbox deleted" not in result.stdout


def test_cli_sbx_064_recreate_yes_calls_service_and_reports_metadata(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["sandbox", "recreate", "e2e-recreate", "--yes"],
        delete_recreate_environment,
    )
    assert result.returncode == 0, result.stderr
    assert "Sandbox recreated." in result.stdout
    assert "Name:                e2e-recreate" in result.stdout
    assert _calls(delete_recreate_environment) == [
        {"operation": "recreate", "name": "e2e-recreate"}
    ]


def test_cli_sbx_065_recreate_without_yes_is_non_destructive(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["sandbox", "recreate", "e2e-no-confirm"],
        delete_recreate_environment,
    )
    assert result.returncode != 0
    assert "sandbox recreate requires --yes" in result.stderr
    assert _calls(delete_recreate_environment) == []


def test_cli_sbx_066_recreate_help_lists_confirmation_option(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    result = _run(
        mcpctl_executable,
        ["sandbox", "recreate", "--help"],
        delete_recreate_environment,
    )
    assert result.returncode == 0
    assert "usage: mcpctl sandbox recreate" in result.stdout
    assert "--yes" in result.stdout
    assert _calls(delete_recreate_environment) == []


def test_cli_sbx_067_recreate_host_backed_metadata_is_reported(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    delete_recreate_environment["MCPCTL_E2E_SERVICE_MODE"] = "host"
    result = _run(
        mcpctl_executable,
        ["sandbox", "recreate", "e2e-host", "--yes"],
        delete_recreate_environment,
    )
    assert result.returncode == 0, result.stderr
    assert any(
        line.startswith("Profile:") and line.split()[-1] == "browser"
        for line in result.stdout.splitlines()
    )
    assert "Host workspace ID:   workspace-e2e-fixture" in result.stdout
    assert "Sandbox path:        /workspace/project" in result.stdout


def test_cli_sbx_068_recreate_standalone_metadata_is_reported(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    delete_recreate_environment["MCPCTL_E2E_SERVICE_MODE"] = "standalone"
    result = _run(
        mcpctl_executable,
        ["sandbox", "recreate", "e2e-standalone", "--yes"],
        delete_recreate_environment,
    )
    assert result.returncode == 0, result.stderr
    assert any(
        line.startswith("Profile:") and line.split()[-1] == "browser"
        for line in result.stdout.splitlines()
    )
    assert "Host workspace ID:" not in result.stdout
    assert "Sandbox path:        /workspace/project" in result.stdout


def test_cli_sbx_069_recreate_missing_returns_nonzero(
    mcpctl_executable: str, delete_recreate_environment: dict[str, str]
) -> None:
    delete_recreate_environment["MCPCTL_E2E_SERVICE_MODE"] = "recreate-missing"
    result = _run(
        mcpctl_executable,
        ["sandbox", "recreate", "e2e-missing", "--yes"],
        delete_recreate_environment,
    )
    assert result.returncode != 0
    assert "e2e-missing" in result.stderr
    assert "not found" in result.stderr.lower()
    assert "Sandbox recreated." not in result.stdout


@pytest.mark.parametrize(
    ("mode", "diagnostic"),
    [("recreate-failure", "synthetic failure"), ("invalid-json", "invalid JSON")],
)
def test_cli_sbx_070_recreate_failure_reports_error_without_false_success(
    mcpctl_executable: str,
    delete_recreate_environment: dict[str, str],
    mode: str,
    diagnostic: str,
) -> None:
    delete_recreate_environment["MCPCTL_E2E_SERVICE_MODE"] = mode
    result = _run(
        mcpctl_executable,
        ["sandbox", "recreate", "e2e-interrupted", "--yes"],
        delete_recreate_environment,
    )
    assert result.returncode != 0
    assert diagnostic.lower() in result.stderr.lower()
    assert "Sandbox recreated." not in result.stdout
