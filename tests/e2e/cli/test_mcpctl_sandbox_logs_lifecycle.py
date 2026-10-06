from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Iterator

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMAND_TIMEOUT_SECONDS = 30
LIFECYCLE_TIMEOUT_SECONDS = 180
SANDBOX_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,18}$")
PROJECT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")

FAKE_OPENSHELL_SOURCE = r"""
import json
import os
import sys
from pathlib import Path

argv_path = Path(os.environ["MCPCTL_E2E_ARGV_FILE"])
with argv_path.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\n")
sys.stdout.write(os.environ.get("MCPCTL_E2E_STDOUT", ""))
sys.stderr.write(os.environ.get("MCPCTL_E2E_STDERR", ""))
raise SystemExit(int(os.environ.get("MCPCTL_E2E_EXIT_CODE", "0")))
"""


def _is_test_project_name(value: str) -> bool:
    return (
        PROJECT_NAME_PATTERN.fullmatch(value) is not None
        and re.search(r"(?:e2e|test)", value, re.IGNORECASE) is not None
        and "prod" not in value.lower()
    )


def _run_mcpctl(
    executable: str,
    arguments: list[str],
    environment: dict[str, str],
    *,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


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
def sandbox_cli_environment(tmp_path: Path) -> dict[str, str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_openshell = fake_bin / "openshell"
    fake_openshell.write_text(
        f"#!{sys.executable}\n{FAKE_OPENSHELL_SOURCE}",
        encoding="utf-8",
    )
    fake_openshell.chmod(0o755)

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
    environment["PATH"] = os.pathsep.join([str(fake_bin), environment.get("PATH", "")])
    environment["MCPCTL_E2E_ARGV_FILE"] = str(tmp_path / "openshell-argv.jsonl")
    environment["MCPCTL_E2E_EXIT_CODE"] = "0"
    environment["MCPCTL_E2E_STDOUT"] = ""
    environment["MCPCTL_E2E_STDERR"] = ""
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["NO_COLOR"] = "1"
    environment["XDG_CONFIG_HOME"] = str(config_home)
    environment["XDG_STATE_HOME"] = str(state_home)
    environment["MCP_CONFIG_DIR"] = str(mcp_config_dir)
    environment["MCP_STATE_DIR"] = str(mcp_state_dir)
    environment["WORKSPACE_GRANTS_DIR"] = str(workspace_grants_dir)
    environment.pop("OPENSHELL_GATEWAY", None)
    environment.pop("OPENSHELL_GATEWAY_ENDPOINT", None)
    environment.pop("OPENSHELL_GATEWAY_INSECURE", None)
    return environment


def _recorded_openshell_invocations(
    environment: dict[str, str],
) -> list[list[str]]:
    argv_path = Path(environment["MCPCTL_E2E_ARGV_FILE"])
    if not argv_path.is_file():
        return []
    invocations = [
        json.loads(line)
        for line in argv_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert all(isinstance(item, list) for item in invocations)
    assert all(
        all(isinstance(argument, str) for argument in item) for item in invocations
    )
    return invocations


def _assert_fake_failure(
    executable: str,
    arguments: list[str],
    environment: dict[str, str],
    expected_invocations: list[list[str]],
    *,
    diagnostic: str = "ERROR: synthetic OpenShell failure\n",
) -> None:
    child_environment = environment.copy()
    child_environment["MCPCTL_E2E_EXIT_CODE"] = "2"
    child_environment["MCPCTL_E2E_STDERR"] = diagnostic
    result = _run_mcpctl(executable, arguments, child_environment)
    assert result.returncode == 2
    assert diagnostic in result.stderr
    assert result.stdout == ""
    assert _recorded_openshell_invocations(child_environment) == expected_invocations


def test_cli_sbx_040_logs_delegates_to_openshell(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    environment = sandbox_cli_environment.copy()
    environment["MCPCTL_E2E_STDOUT"] = "synthetic sandbox log line\n"
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "logs", "e2e-logs-fixture"],
        environment,
    )
    assert result.returncode == 0
    assert result.stdout == "synthetic sandbox log line\n"
    assert _recorded_openshell_invocations(environment) == [
        ["logs", "e2e-logs-fixture"]
    ]


def test_cli_sbx_041_logs_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "logs", "--help"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert "usage: mcpctl sandbox logs" in result.stdout
    assert "name" in result.stdout
    assert _recorded_openshell_invocations(sandbox_cli_environment) == []


def test_cli_sbx_042_start_delegates_to_openshell(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "start", "e2e-start-fixture"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert _recorded_openshell_invocations(sandbox_cli_environment) == [
        ["sandbox", "start", "e2e-start-fixture"]
    ]


def test_cli_sbx_043_start_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "start", "--help"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert "usage: mcpctl sandbox start" in result.stdout
    assert "name" in result.stdout
    assert _recorded_openshell_invocations(sandbox_cli_environment) == []


def test_cli_sbx_044_stop_delegates_to_openshell(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "stop", "e2e-stop-fixture"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert _recorded_openshell_invocations(sandbox_cli_environment) == [
        ["sandbox", "stop", "e2e-stop-fixture"]
    ]


def test_cli_sbx_045_stop_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "stop", "--help"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert "usage: mcpctl sandbox stop" in result.stdout
    assert "name" in result.stdout
    assert _recorded_openshell_invocations(sandbox_cli_environment) == []


def test_cli_sbx_046_restart_stops_then_starts_and_propagates_stop_failure(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    name = "e2e-restart-fixture"
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "restart", name],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert _recorded_openshell_invocations(sandbox_cli_environment) == [
        ["sandbox", "stop", name],
        ["sandbox", "start", name],
    ]

    failure_environment = sandbox_cli_environment.copy()
    failure_environment["MCPCTL_E2E_EXIT_CODE"] = "2"
    failure_environment["MCPCTL_E2E_STDERR"] = "synthetic stop failure\n"
    failure_environment["MCPCTL_E2E_ARGV_FILE"] = str(
        Path(sandbox_cli_environment["MCPCTL_E2E_ARGV_FILE"]).with_name(
            "restart-failure.jsonl"
        )
    )
    failed = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "restart", name],
        failure_environment,
    )
    assert failed.returncode == 2
    assert "synthetic stop failure" in failed.stderr
    assert _recorded_openshell_invocations(failure_environment) == [
        ["sandbox", "stop", name]
    ]


def test_cli_sbx_047_restart_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "restart", "--help"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert "usage: mcpctl sandbox restart" in result.stdout
    assert "name" in result.stdout
    assert _recorded_openshell_invocations(sandbox_cli_environment) == []


def test_cli_sbx_048_repair_delegates_to_start(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "repair", "e2e-repair-fixture"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert _recorded_openshell_invocations(sandbox_cli_environment) == [
        ["sandbox", "start", "e2e-repair-fixture"]
    ]


def test_cli_sbx_049_repair_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "repair", "--help"],
        sandbox_cli_environment,
    )
    assert result.returncode == 0
    assert "usage: mcpctl sandbox repair" in result.stdout
    assert "name" in result.stdout
    assert _recorded_openshell_invocations(sandbox_cli_environment) == []


@pytest.mark.parametrize(
    ("operation", "expected_invocation"),
    [
        ("logs", ["logs", "e2e-missing-fixture"]),
        ("start", ["sandbox", "start", "e2e-missing-fixture"]),
        ("stop", ["sandbox", "stop", "e2e-missing-fixture"]),
        ("restart", ["sandbox", "stop", "e2e-missing-fixture"]),
        ("repair", ["sandbox", "start", "e2e-missing-fixture"]),
    ],
)
def test_cli_sbx_050_missing_sandbox_operation_propagates_failure(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
    operation: str,
    expected_invocation: list[str],
) -> None:
    _assert_fake_failure(
        mcpctl_executable,
        ["sandbox", operation, "e2e-missing-fixture"],
        sandbox_cli_environment,
        [expected_invocation],
        diagnostic="ERROR: Sandbox 'e2e-missing-fixture' was not found.\n",
    )


@pytest.fixture
def isolated_openshell_environment(
    tmp_path: Path,
) -> dict[str, str]:
    if os.environ.get("MCPCTL_E2E_ALLOW_MUTATING") != "1":
        pytest.skip(
            "BLOCKED: set MCPCTL_E2E_ALLOW_MUTATING=1 only after "
            "preparing a disposable OpenShell runtime."
        )
    if os.environ.get("MCPCTL_E2E_ISOLATED") != "1":
        pytest.skip(
            "BLOCKED: confirm the dedicated OpenShell configuration "
            "and Docker context with MCPCTL_E2E_ISOLATED=1."
        )

    docker_context = os.environ.get("MCPCTL_E2E_DOCKER_CONTEXT", "")
    if (
        not docker_context
        or re.search(r"(?:e2e|test)", docker_context, re.IGNORECASE) is None
        or "prod" in docker_context.lower()
    ):
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_DOCKER_CONTEXT must identify a "
            "disposable test Docker context."
        )

    config_value = os.environ.get("MCPCTL_E2E_OPENSHELL_CONFIG_HOME", "")
    if not config_value:
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_OPENSHELL_CONFIG_HOME must point to "
            "a dedicated OpenShell test configuration."
        )
    config_home = Path(config_value).expanduser()
    if not config_home.is_absolute():
        pytest.skip("BLOCKED: MCPCTL_E2E_OPENSHELL_CONFIG_HOME must be absolute.")
    config_home = config_home.resolve()
    if config_home == (Path.home() / ".config").resolve():
        pytest.skip(
            "BLOCKED: use a dedicated OpenShell test configuration, "
            "not the default user configuration."
        )
    if (
        re.search(r"(?:e2e|test)", config_home.name, re.IGNORECASE) is None
        or "prod" in str(config_home).lower()
    ):
        pytest.skip(
            "BLOCKED: the OpenShell configuration directory must be "
            "clearly test-named and must not be production-named."
        )
    if not config_home.is_dir() or not any(config_home.iterdir()):
        pytest.skip(
            "BLOCKED: the dedicated OpenShell configuration directory "
            "must exist and contain its configured gateway data."
        )

    project_name = os.environ.get("MCPCTL_E2E_COMPOSE_PROJECT", "")
    if not _is_test_project_name(project_name):
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_COMPOSE_PROJECT must be a valid "
            "test-named project, not a production project."
        )

    try:
        context_result = subprocess.run(
            ["docker", "context", "inspect", docker_context],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip(
            "BLOCKED: Docker is unavailable or the test context could not be inspected."
        )
    if context_result.returncode != 0:
        pytest.skip(
            "BLOCKED: the configured test Docker context does not exist "
            "or cannot be inspected."
        )

    environment = os.environ.copy()
    environment["XDG_CONFIG_HOME"] = str(config_home)
    environment["XDG_STATE_HOME"] = str(tmp_path / "xdg-state")
    environment["COMPOSE_PROJECT_NAME"] = project_name
    environment["DOCKER_CONTEXT"] = docker_context
    Path(environment["XDG_STATE_HOME"]).mkdir(parents=True, exist_ok=True)
    return environment


def _live_sandbox_status(
    executable: str,
    name: str,
    environment: dict[str, str],
) -> dict[str, object]:
    result = _run_mcpctl(
        executable,
        ["sandbox", "status", name, "--json"],
        environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, (
        f"Could not query sandbox {name!r}.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert payload.get("name") == name
    assert isinstance(payload.get("status"), str)
    return payload


def _cleanup_live_sandbox(
    executable: str,
    name: str,
    environment: dict[str, str],
    *,
    required: bool,
) -> None:
    result = _run_mcpctl(
        executable,
        ["sandbox", "delete", name, "--json"],
        environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    if result.returncode == 0:
        return
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    if any(
        marker in diagnostic
        for marker in (
            "not found",
            "does not exist",
            "no such sandbox",
            "unknown sandbox",
        )
    ):
        return
    if required:
        pytest.fail(
            f"Could not delete test sandbox {name!r} during cleanup.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


@pytest.fixture
def live_sandbox(
    mcpctl_executable: str,
    isolated_openshell_environment: dict[str, str],
) -> Iterator[tuple[str, dict[str, str]]]:
    name = f"e2e-{uuid.uuid4().hex[:8]}"
    assert SANDBOX_NAME_PATTERN.fullmatch(name) is not None
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "create", name, "--standalone", "--json"],
        isolated_openshell_environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        _cleanup_live_sandbox(
            mcpctl_executable,
            name,
            isolated_openshell_environment,
            required=False,
        )
        pytest.fail(
            f"Could not create isolated lifecycle sandbox {name!r}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    try:
        payload = json.loads(result.stdout)
        assert isinstance(payload, dict)
        assert payload.get("name") == name
        status = _live_sandbox_status(
            mcpctl_executable,
            name,
            isolated_openshell_environment,
        )
        assert status["status"] == "Ready"
        yield name, isolated_openshell_environment
    finally:
        _cleanup_live_sandbox(
            mcpctl_executable,
            name,
            isolated_openshell_environment,
            required=True,
        )


def test_cli_sbx_051_start_stopped_sandbox_returns_to_ready(
    mcpctl_executable: str,
    live_sandbox: tuple[str, dict[str, str]],
) -> None:
    name, environment = live_sandbox
    stopped = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "stop", name],
        environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    assert stopped.returncode == 0, f"{stopped.stdout}\n{stopped.stderr}"
    assert (
        _live_sandbox_status(mcpctl_executable, name, environment)["status"]
        == "Stopped"
    )

    started = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "start", name],
        environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    assert started.returncode == 0, f"{started.stdout}\n{started.stderr}"
    assert (
        _live_sandbox_status(mcpctl_executable, name, environment)["status"] == "Ready"
    )


def test_cli_sbx_052_stop_retains_sandbox_state(
    mcpctl_executable: str,
    live_sandbox: tuple[str, dict[str, str]],
) -> None:
    name, environment = live_sandbox
    before = _live_sandbox_status(mcpctl_executable, name, environment)
    assert before["status"] == "Ready"
    stopped = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "stop", name],
        environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    assert stopped.returncode == 0, f"{stopped.stdout}\n{stopped.stderr}"
    after = _live_sandbox_status(mcpctl_executable, name, environment)
    assert after["status"] == "Stopped"
    assert after["name"] == name
    assert after.get("id") == before.get("id")


def test_cli_sbx_053_restart_returns_to_ready_and_remains_usable(
    mcpctl_executable: str,
    live_sandbox: tuple[str, dict[str, str]],
) -> None:
    name, environment = live_sandbox
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "restart", name],
        environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert (
        _live_sandbox_status(mcpctl_executable, name, environment)["status"] == "Ready"
    )
    usable = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "exec", name, "--", "/bin/true"],
        environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    assert usable.returncode == 0, f"{usable.stdout}\n{usable.stderr}"


def test_cli_sbx_054_repair_missing_sandbox_reports_failure(
    mcpctl_executable: str,
    isolated_openshell_environment: dict[str, str],
) -> None:
    name = f"e2e-{uuid.uuid4().hex[:8]}"
    assert SANDBOX_NAME_PATTERN.fullmatch(name) is not None
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "repair", name],
        isolated_openshell_environment,
        timeout=LIFECYCLE_TIMEOUT_SECONDS,
    )
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    assert any(
        marker in diagnostic
        for marker in (
            "not found",
            "does not exist",
            "no such sandbox",
            "unknown sandbox",
        )
    )
    assert "ready" not in diagnostic
