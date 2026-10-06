from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMAND_TIMEOUT_SECONDS = 30

FAKE_OPENSHELL_SOURCE = r"""
from pathlib import Path
import json
import os
import sys

Path(os.environ["MCPCTL_E2E_ARGV_FILE"]).write_text(
    json.dumps(sys.argv[1:], ensure_ascii=False),
    encoding="utf-8",
)

sys.stdout.write(os.environ.get("MCPCTL_E2E_STDOUT", ""))
sys.stderr.write(os.environ.get("MCPCTL_E2E_STDERR", ""))

raise SystemExit(int(os.environ.get("MCPCTL_E2E_EXIT_CODE", "0")))
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
    environment["PATH"] = os.pathsep.join(
        [
            str(fake_bin),
            environment.get("PATH", ""),
        ]
    )
    environment["MCPCTL_E2E_ARGV_FILE"] = str(tmp_path / "openshell-argv.json")
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


def _run_mcpctl(
    executable: str,
    arguments: list[str],
    environment: dict[str, str],
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    child_environment = environment.copy()
    child_environment["MCPCTL_E2E_EXIT_CODE"] = str(exit_code)
    child_environment["MCPCTL_E2E_STDOUT"] = stdout
    child_environment["MCPCTL_E2E_STDERR"] = stderr

    # Run the installed console-script source with the active interpreter,
    # avoiding machine-specific shebangs in generated entrypoint scripts.
    return subprocess.run(
        [sys.executable, executable, *arguments],
        cwd=PROJECT_ROOT,
        env=child_environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


def _recorded_openshell_argv(
    environment: dict[str, str],
) -> list[str]:
    argv_path = Path(environment["MCPCTL_E2E_ARGV_FILE"])
    assert argv_path.is_file(), "The fake OpenShell executable was not invoked."

    payload = json.loads(argv_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert all(isinstance(argument, str) for argument in payload)

    return payload


def test_cli_sbx_030_shell_delegates_to_openshell(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "shell", "e2e-shell-fixture"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox shell failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert _recorded_openshell_argv(sandbox_cli_environment) == [
        "sandbox",
        "exec",
        "--name",
        "e2e-shell-fixture",
        "--tty",
        "--",
        "/bin/bash",
        "-l",
    ]


def test_cli_sbx_031_shell_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "shell", "--help"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0
    assert "usage: mcpctl sandbox shell" in result.stdout
    assert "name" in result.stdout
    assert "--help" in result.stdout
    assert not Path(sandbox_cli_environment["MCPCTL_E2E_ARGV_FILE"]).exists()


def test_cli_sbx_032_exec_delegates_requested_command(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "exec",
            "e2e-exec-fixture",
            "--",
            "printf",
            "e2e-exec-ok",
        ],
        sandbox_cli_environment,
        stdout="e2e-exec-ok",
    )

    assert result.returncode == 0, (
        f"Sandbox exec failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout == "e2e-exec-ok"
    assert _recorded_openshell_argv(sandbox_cli_environment) == [
        "sandbox",
        "exec",
        "--name",
        "e2e-exec-fixture",
        "--",
        "printf",
        "e2e-exec-ok",
    ]


def test_cli_sbx_033_exec_preserves_multiple_argument_order(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    command = [
        "printf",
        "%s:%s:%s",
        "first",
        "second",
        "third",
    ]

    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "exec",
            "e2e-args-fixture",
            "--",
            *command,
        ],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox exec failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert _recorded_openshell_argv(sandbox_cli_environment) == [
        "sandbox",
        "exec",
        "--name",
        "e2e-args-fixture",
        "--",
        *command,
    ]


def test_cli_sbx_034_exec_preserves_spaces_and_quoted_arguments(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    command = [
        "python3",
        "-c",
        "pass",
        "two words",
        "single'quote",
        'double"quote',
        "$HOME; touch /tmp/mcpctl-e2e-must-not-run && echo unsafe",
        "",
    ]

    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "exec",
            "e2e-quoted-fixture",
            "--",
            *command,
        ],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox exec failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    forwarded = _recorded_openshell_argv(sandbox_cli_environment)
    assert forwarded == [
        "sandbox",
        "exec",
        "--name",
        "e2e-quoted-fixture",
        "--",
        *command,
    ]

    forwarded_command = forwarded[5:]
    assert forwarded_command[3] == "two words"
    assert forwarded_command[4] == "single'quote"
    assert forwarded_command[5] == 'double"quote'
    assert forwarded_command[6] == (
        "$HOME; touch /tmp/mcpctl-e2e-must-not-run && echo unsafe"
    )
    assert forwarded_command[7] == ""


def test_cli_sbx_035_exec_forwards_child_command_options(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "exec",
            "e2e-version-fixture",
            "--",
            "python3",
            "--version",
        ],
        sandbox_cli_environment,
    )

    assert result.returncode == 0, (
        f"Sandbox exec failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert _recorded_openshell_argv(sandbox_cli_environment) == [
        "sandbox",
        "exec",
        "--name",
        "e2e-version-fixture",
        "--",
        "python3",
        "--version",
    ]


def test_cli_sbx_036_exec_propagates_nonzero_exit_code(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "exec",
            "e2e-failure-fixture",
            "--",
            "test-child",
            "--fail",
        ],
        sandbox_cli_environment,
        exit_code=23,
        stdout="partial child output\n",
        stderr="test child failed\n",
    )

    assert result.returncode == 23
    assert result.stdout == "partial child output\n"
    assert result.stderr == "test child failed\n"
    assert _recorded_openshell_argv(sandbox_cli_environment) == [
        "sandbox",
        "exec",
        "--name",
        "e2e-failure-fixture",
        "--",
        "test-child",
        "--fail",
    ]


def test_cli_sbx_037_exec_without_command_returns_validation_error(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "exec", "e2e-empty-fixture"],
        sandbox_cli_environment,
    )

    assert result.returncode == 2
    assert "ERROR: sandbox exec requires a command after '--'." in result.stderr
    assert result.stdout == ""
    assert not Path(sandbox_cli_environment["MCPCTL_E2E_ARGV_FILE"]).exists()


def test_cli_sbx_038_exec_missing_sandbox_propagates_failure(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "exec",
            "e2e-missing",
            "--",
            "true",
        ],
        sandbox_cli_environment,
        exit_code=1,
        stderr="sandbox 'e2e-missing' not found\n",
    )

    assert result.returncode == 1
    assert "sandbox 'e2e-missing' not found" in result.stderr
    assert _recorded_openshell_argv(sandbox_cli_environment) == [
        "sandbox",
        "exec",
        "--name",
        "e2e-missing",
        "--",
        "true",
    ]


def test_cli_sbx_039_exec_help(
    mcpctl_executable: str,
    sandbox_cli_environment: dict[str, str],
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "exec", "--help"],
        sandbox_cli_environment,
    )

    assert result.returncode == 0
    assert "usage: mcpctl sandbox exec" in result.stdout
    assert "name" in result.stdout
    assert "exec_command" in result.stdout
    assert not Path(sandbox_cli_environment["MCPCTL_E2E_ARGV_FILE"]).exists()
