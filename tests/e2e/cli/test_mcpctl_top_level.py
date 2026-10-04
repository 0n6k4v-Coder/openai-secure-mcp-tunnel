from __future__ import annotations

import os
import re
import selectors
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_TEST_PROJECT = "local-mcp-server-e2e-status"
COMMAND_TIMEOUT_SECONDS = 30
MUTATING_TIMEOUT_SECONDS = 240
INTERRUPT_PROMPT_TIMEOUT_SECONDS = 90
PROJECT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")


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
            "Install the project with uv sync before running E2E tests."
        )
    return str(Path(candidate).resolve())


def _command_environment(
    tmp_path: Path,
    *,
    project_name: str = REPORT_TEST_PROJECT,
) -> dict[str, str]:
    environment = os.environ.copy()
    config_home = tmp_path / "xdg-config"
    state_home = tmp_path / "xdg-state"
    environment["XDG_CONFIG_HOME"] = str(config_home)
    environment["XDG_STATE_HOME"] = str(state_home)
    environment["MCP_CONFIG_DIR"] = str(tmp_path / "compose-mcp-config")
    environment["MCP_STATE_DIR"] = str(tmp_path / "compose-mcp-state")
    environment["WORKSPACE_GRANTS_DIR"] = str(tmp_path / "compose-workspace-grants")
    environment["COMPOSE_PROJECT_NAME"] = project_name
    environment["PYTHONUNBUFFERED"] = "1"
    for variable in ("MCP_CONFIG_DIR", "MCP_STATE_DIR", "WORKSPACE_GRANTS_DIR"):
        Path(environment[variable]).mkdir(parents=True, exist_ok=True)
    # Compose validates the declared secret's source path even when the test
    # deliberately skips starting the tunnel-client service. This is a dummy,
    # disposable file under the temporary XDG config root, never a real secret.
    credentials = (
        config_home / "local-mcp-server" / "mcp-clients" / "openai" / "credentials"
    )
    credentials.parent.mkdir(parents=True, exist_ok=True)
    credentials.write_text("e2e-disposable-credential\n", encoding="utf-8")
    credentials.chmod(0o600)
    docker_context = os.environ.get("MCPCTL_E2E_DOCKER_CONTEXT")
    if docker_context:
        environment["DOCKER_CONTEXT"] = docker_context
    return environment


def _is_test_project_name(value: str) -> bool:
    return (
        PROJECT_NAME_PATTERN.fullmatch(value) is not None
        and re.search(r"(?:e2e|test)", value) is not None
        and "prod" not in value
    )


def _project_name_from_env_file() -> str | None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return None
    content = env_file.read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^\s*COMPOSE_PROJECT_NAME\s*=\s*['\"]?([a-z0-9][a-z0-9_-]*)",
        content,
    )
    return match.group(1) if match else None


def _mutating_environment(tmp_path: Path) -> dict[str, str]:
    if os.environ.get("MCPCTL_E2E_ALLOW_MUTATING") != "1":
        pytest.skip(
            "BLOCKED: set MCPCTL_E2E_ALLOW_MUTATING=1 only after "
            "preparing a disposable E2E runtime."
        )
    if os.environ.get("MCPCTL_E2E_ISOLATED") != "1":
        pytest.skip(
            "BLOCKED: confirm the disposable runtime, test-only .env values, "
            "and non-conflicting host ports with MCPCTL_E2E_ISOLATED=1."
        )

    project_name = os.environ.get("MCPCTL_E2E_COMPOSE_PROJECT", "")
    if not _is_test_project_name(project_name):
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_COMPOSE_PROJECT must be a valid test-named "
            "Compose project, not a production project."
        )

    docker_context = os.environ.get("MCPCTL_E2E_DOCKER_CONTEXT", "")
    if (
        not docker_context
        or not re.search(r"(?:e2e|test)", docker_context, re.IGNORECASE)
        or "prod" in docker_context.lower()
    ):
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_DOCKER_CONTEXT must name a disposable test Docker context."
        )

    env_project = _project_name_from_env_file()
    if env_project is None or not _is_test_project_name(env_project):
        pytest.skip(
            "BLOCKED: repository .env must contain a test-only COMPOSE_PROJECT_NAME."
        )

    environment = _command_environment(tmp_path, project_name=project_name)
    environment["DOCKER_CONTEXT"] = docker_context
    return environment


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.communicate()


def _run_process(
    command: list[str],
    *,
    environment: dict[str, str],
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        pytest.fail(f"Command {command[0]!r} exceeded its {timeout}-second timeout.")
    return subprocess.CompletedProcess(
        args=command,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _run_mcpctl(
    executable: str,
    arguments: list[str],
    *,
    tmp_path: Path,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    input_text: str | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return _run_process(
        [executable, *arguments],
        environment=environment or _command_environment(tmp_path),
        timeout=timeout,
        input_text=input_text,
    )


def _cleanup_compose_project(environment: dict[str, str]) -> None:
    command = [
        "docker",
        "compose",
        "--file",
        str(PROJECT_ROOT / "deploy" / "compose.yaml"),
        "--env-file",
        str(PROJECT_ROOT / ".env"),
        "down",
        "--remove-orphans",
        "--timeout",
        "10",
    ]
    result = _run_process(command, environment=environment, timeout=60)
    assert result.returncode == 0, (
        "Docker Compose cleanup failed for the isolated E2E project."
    )


def _interrupt_setup_at_prompt(
    executable: str,
    environment: dict[str, str],
) -> tuple[int, bytes]:
    process = subprocess.Popen(
        [executable, "setup"],
        cwd=PROJECT_ROOT,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name == "posix"),
    )
    if process.stdout is None:
        _terminate_process_tree(process)
        pytest.fail("Could not capture setup stdout.")

    output = bytearray()
    deadline = time.monotonic() + INTERRUPT_PROMPT_TIMEOUT_SECONDS
    interrupted = False
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            events = selector.select(min(0.5, max(0.0, remaining)))
            if not events and process.poll() is not None:
                break
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if b"Select [1]:" in output:
                    process.send_signal(signal.SIGINT)
                    interrupted = True
                    break
            if interrupted:
                break

    if not interrupted:
        _terminate_process_tree(process)
        pytest.fail(
            "mcpctl setup did not reach its interactive prompt before exiting or timing out."
        )
    try:
        _, stderr = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        pytest.fail("mcpctl setup did not exit after SIGINT.")
    return process.returncode, stderr


def test_cli_mcp_001_setup(mcpctl_executable: str, tmp_path: Path) -> None:
    environment = _mutating_environment(tmp_path)
    try:
        result = _run_mcpctl(
            mcpctl_executable,
            ["setup"],
            tmp_path=tmp_path,
            environment=environment,
            timeout=MUTATING_TIMEOUT_SECONDS,
            input_text="2\n",
        )
        assert result.returncode == 0, "mcpctl setup did not complete successfully."
        assert "Local MCP Server Setup" in result.stdout
        assert "Core Services" in result.stdout
    finally:
        _cleanup_compose_project(environment)


def test_cli_mcp_002_status(mcpctl_executable: str, tmp_path: Path) -> None:
    result = _run_mcpctl(mcpctl_executable, ["status"], tmp_path=tmp_path, timeout=60)
    assert result.returncode in {0, 2}
    assert "Local MCP Lifecycle" in result.stdout
    assert "OpenShell TLS" in result.stdout
    assert "OpenShell Gateway" in result.stdout
    assert "MCP Server" in result.stdout
    assert "Overall" in result.stdout


def test_cli_mcp_003_repair(mcpctl_executable: str, tmp_path: Path) -> None:
    environment = _mutating_environment(tmp_path)
    try:
        result = _run_mcpctl(
            mcpctl_executable,
            ["repair"],
            tmp_path=tmp_path,
            environment=environment,
            timeout=MUTATING_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, "mcpctl repair did not complete successfully."
        assert "Local MCP Server Repair" in result.stdout
        assert "Core Services" in result.stdout
    finally:
        _cleanup_compose_project(environment)


def test_cli_mcp_004_long_help(mcpctl_executable: str, tmp_path: Path) -> None:
    result = _run_mcpctl(mcpctl_executable, ["--help"], tmp_path=tmp_path)
    assert result.returncode == 0
    assert "usage: mcpctl" in result.stdout
    assert "setup" in result.stdout
    assert "status" in result.stdout
    assert "repair" in result.stdout


def test_cli_mcp_005_short_help(mcpctl_executable: str, tmp_path: Path) -> None:
    result = _run_mcpctl(mcpctl_executable, ["-h"], tmp_path=tmp_path)
    assert result.returncode == 0
    assert "usage: mcpctl" in result.stdout
    assert "setup" in result.stdout
    assert "status" in result.stdout
    assert "repair" in result.stdout


def test_cli_mcp_006_setup_help(mcpctl_executable: str, tmp_path: Path) -> None:
    result = _run_mcpctl(mcpctl_executable, ["setup", "--help"], tmp_path=tmp_path)
    assert result.returncode == 0
    assert "usage: mcpctl setup" in result.stdout
    assert "-h, --help" in result.stdout


def test_cli_mcp_007_status_help(mcpctl_executable: str, tmp_path: Path) -> None:
    result = _run_mcpctl(mcpctl_executable, ["status", "--help"], tmp_path=tmp_path)
    assert result.returncode == 0
    assert "usage: mcpctl status" in result.stdout
    assert "-h, --help" in result.stdout


def test_cli_mcp_008_repair_help(mcpctl_executable: str, tmp_path: Path) -> None:
    result = _run_mcpctl(mcpctl_executable, ["repair", "--help"], tmp_path=tmp_path)
    assert result.returncode == 0
    assert "usage: mcpctl repair" in result.stdout
    assert "-h, --help" in result.stdout


def test_cli_mcp_009_unknown_top_level_command(
    mcpctl_executable: str,
    tmp_path: Path,
) -> None:
    result = _run_mcpctl(mcpctl_executable, ["unknown-e2e-command"], tmp_path=tmp_path)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "invalid choice" in result.stderr


def test_cli_mcp_010_missing_top_level_command(
    mcpctl_executable: str,
    tmp_path: Path,
) -> None:
    result = _run_mcpctl(mcpctl_executable, [], tmp_path=tmp_path)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "required: command" in result.stderr


def test_cli_mcp_011_unsupported_top_level_command_flags(
    mcpctl_executable: str,
    tmp_path: Path,
) -> None:
    results = [
        _run_mcpctl(
            mcpctl_executable,
            [command, "--unsupported-e2e-option"],
            tmp_path=tmp_path,
        )
        for command in ("setup", "status", "repair")
    ]
    assert all(result.returncode == 2 for result in results), (
        "At least one top-level command accepted an unsupported flag."
    )
    assert all("unrecognized arguments" in result.stderr for result in results), (
        "At least one unsupported flag did not produce an argparse error."
    )


def test_cli_mcp_012_interrupt_interactive_command(
    mcpctl_executable: str,
    tmp_path: Path,
) -> None:
    environment = _mutating_environment(tmp_path)
    try:
        returncode, stderr = _interrupt_setup_at_prompt(mcpctl_executable, environment)
        assert returncode == 130
        assert b"Cancelled." in stderr
    finally:
        _cleanup_compose_project(environment)
