from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMAND_TIMEOUT_SECONDS = 30
CREATE_TIMEOUT_SECONDS = 180
SANDBOX_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,18}$")
PROJECT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")


def _is_test_name(value: str) -> bool:
    return (
        PROJECT_NAME_PATTERN.fullmatch(value) is not None
        and re.search(r"(?:e2e|test)", value, re.IGNORECASE) is not None
        and "prod" not in value.lower()
    )


def _run_mcpctl(
    executable: str,
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *arguments],
        cwd=PROJECT_ROOT,
        env=environment or os.environ.copy(),
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
            "Install the project with uv sync before running E2E tests."
        )

    return str(Path(candidate).resolve())


@pytest.fixture
def sandbox_e2e_environment(
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

    docker_context = os.environ.get(
        "MCPCTL_E2E_DOCKER_CONTEXT",
        "",
    )
    if (
        not docker_context
        or re.search(r"(?:e2e|test)", docker_context, re.IGNORECASE)
        is None
        or "prod" in docker_context.lower()
    ):
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_DOCKER_CONTEXT must identify a "
            "disposable test Docker context."
        )

    config_value = os.environ.get(
        "MCPCTL_E2E_OPENSHELL_CONFIG_HOME",
        "",
    )
    if not config_value:
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_OPENSHELL_CONFIG_HOME must point to "
            "a dedicated OpenShell test configuration."
        )

    config_home = Path(config_value).expanduser()
    if not config_home.is_absolute():
        pytest.skip(
            "BLOCKED: MCPCTL_E2E_OPENSHELL_CONFIG_HOME must be absolute."
        )

    config_home = config_home.resolve()
    default_config_home = (Path.home() / ".config").resolve()

    if config_home == default_config_home:
        pytest.skip(
            "BLOCKED: use a dedicated OpenShell test configuration, "
            "not the default user configuration."
        )

    if (
        re.search(r"(?:e2e|test)", config_home.name, re.IGNORECASE)
        is None
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

    project_name = os.environ.get(
        "MCPCTL_E2E_COMPOSE_PROJECT",
        "",
    )
    if not _is_test_name(project_name):
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
            "BLOCKED: Docker is unavailable or the test context "
            "could not be inspected."
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

    for variable in ("XDG_STATE_HOME",):
        Path(environment[variable]).mkdir(
            parents=True,
            exist_ok=True,
        )

    return environment


@pytest.fixture
def sandbox_name() -> str:
    name = f"e2e-{uuid.uuid4().hex[:8]}"
    assert SANDBOX_NAME_PATTERN.fullmatch(name) is not None
    return name


@pytest.fixture
def workspace_grant(
    mcpctl_executable: str,
    sandbox_e2e_environment: dict[str, str],
    tmp_path: Path,
):
    host_workspace = tmp_path / "host-workspace"
    host_workspace.mkdir()

    result = _run_mcpctl(
        mcpctl_executable,
        ["workspace", "authorize", str(host_workspace)],
        environment=sandbox_e2e_environment,
        timeout=CREATE_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, (
        "Could not authorize the isolated test workspace.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)

    workspace_id = payload.get("workspace_id")
    assert isinstance(workspace_id, str) and workspace_id

    try:
        yield workspace_id
    finally:
        revoke_result = _run_mcpctl(
            mcpctl_executable,
            ["workspace", "revoke", workspace_id],
            environment=sandbox_e2e_environment,
            timeout=CREATE_TIMEOUT_SECONDS,
        )

        assert revoke_result.returncode == 0, (
            "Could not revoke the test workspace grant.\n"
            f"stdout: {revoke_result.stdout}\n"
            f"stderr: {revoke_result.stderr}"
        )

        revoked_payload = json.loads(revoke_result.stdout)
        assert revoked_payload["workspace_id"] == workspace_id
        assert revoked_payload["revoked"] is True


def _sandbox_status(
    executable: str,
    name: str,
    environment: dict[str, str],
) -> dict[str, object]:
    result = _run_mcpctl(
        executable,
        ["sandbox", "status", name, "--json"],
        environment=environment,
        timeout=CREATE_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, (
        f"Could not query the created sandbox {name!r}.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert payload.get("name") == name

    return payload


def _cleanup_sandbox(
    executable: str,
    name: str,
    environment: dict[str, str],
    *,
    creation_succeeded: bool,
) -> None:
    result = _run_mcpctl(
        executable,
        ["sandbox", "delete", name, "--json"],
        environment=environment,
        timeout=CREATE_TIMEOUT_SECONDS,
    )

    if result.returncode == 0:
        return

    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    missing_messages = (
        "not found",
        "does not exist",
        "no such sandbox",
        "unknown sandbox",
    )

    if any(message in diagnostic for message in missing_messages):
        return

    if creation_succeeded:
        pytest.fail(
            f"Could not delete test sandbox {name!r} during cleanup.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


def _create_and_verify(
    executable: str,
    name: str,
    arguments: list[str],
    environment: dict[str, str],
    *,
    expected_profile: str,
    expected_workspace_id: str | None,
    json_output: bool,
    expected_text: str | None = None,
) -> None:
    creation_succeeded = False

    try:
        result = _run_mcpctl(
            executable,
            ["sandbox", "create", name, *arguments],
            environment=environment,
            timeout=CREATE_TIMEOUT_SECONDS,
        )

        assert result.returncode == 0, (
            f"Sandbox creation failed for {name!r}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        creation_succeeded = True

        if json_output:
            created_payload = json.loads(result.stdout)
            assert isinstance(created_payload, dict)
            assert created_payload.get("name") == name
            assert created_payload.get("profile") == expected_profile

            if expected_workspace_id is None:
                assert "host_workspace_id" not in created_payload
            else:
                assert (
                    created_payload.get("host_workspace_id")
                    == expected_workspace_id
                )
        else:
            assert "Sandbox created." in result.stdout
            assert f"Name:                {name}" in result.stdout
            assert f"Profile:             {expected_profile}" in result.stdout

            if expected_text is not None:
                assert expected_text in result.stdout

            if expected_workspace_id is not None:
                assert (
                    f"Host workspace ID:   {expected_workspace_id}"
                    in result.stdout
                )

        status = _sandbox_status(
            executable,
            name,
            environment,
        )

        assert status.get("profile") == expected_profile

        if expected_workspace_id is None:
            assert "host_workspace_id" not in status

            workspace = status.get("workspace")
            assert isinstance(workspace, dict)
            assert workspace.get("type") == "sandbox"
        else:
            assert (
                status.get("host_workspace_id")
                == expected_workspace_id
            )

            host_workspace = status.get("host_workspace")
            assert isinstance(host_workspace, dict)
            assert host_workspace.get("id") == expected_workspace_id
            assert host_workspace.get("authorized") is True

    finally:
        _cleanup_sandbox(
            executable,
            name,
            environment,
            creation_succeeded=creation_succeeded,
        )


def test_cli_sbx_001_standalone_create(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--standalone"],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=None,
        json_output=False,
    )


def test_cli_sbx_002_host_workspace_create(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
    workspace_grant: str,
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--workspace", workspace_grant],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=workspace_grant,
        json_output=False,
    )


def test_cli_sbx_003_workspace_id_preserved(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
    workspace_grant: str,
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--workspace", workspace_grant],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=workspace_grant,
        json_output=False,
    )


def test_cli_sbx_004_standalone_mode(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--standalone"],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=None,
        json_output=False,
        expected_text="Application workspace: sandbox-local",
    )


def test_cli_sbx_005_default_profile(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--standalone", "--profile", "default"],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=None,
        json_output=False,
    )


def test_cli_sbx_006_browser_profile(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--standalone", "--profile", "browser"],
        sandbox_e2e_environment,
        expected_profile="browser",
        expected_workspace_id=None,
        json_output=False,
    )


def test_cli_sbx_007_omitted_profile_defaults_to_default(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--standalone"],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=None,
        json_output=False,
    )


def test_cli_sbx_008_rejects_unsupported_profile(
    mcpctl_executable: str,
    sandbox_name: str,
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "create",
            sandbox_name,
            "--standalone",
            "--profile",
            "unsupported-e2e-profile",
        ],
    )

    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert "unsupported-e2e-profile" in result.stderr


def test_cli_sbx_009_json_output(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        ["--standalone", "--json"],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=None,
        json_output=True,
    )


def test_cli_sbx_010_requires_workspace_source(
    mcpctl_executable: str,
    sandbox_name: str,
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "create", sandbox_name],
    )

    assert result.returncode == 2
    assert "--workspace" in result.stderr
    assert "--standalone" in result.stderr
    assert "required" in result.stderr


def test_cli_sbx_011_rejects_both_workspace_sources(
    mcpctl_executable: str,
    sandbox_name: str,
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        [
            "sandbox",
            "create",
            sandbox_name,
            "--workspace",
            "ws_e2e_invalid",
            "--standalone",
        ],
    )

    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr


def test_cli_sbx_012_requires_sandbox_name(
    mcpctl_executable: str,
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "create", "--standalone"],
    )

    assert result.returncode == 2
    assert "name" in result.stderr
    assert "required" in result.stderr


def test_cli_sbx_013_rejects_invalid_sandbox_name(
    mcpctl_executable: str,
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "create", "invalid_name", "--standalone"],
    )

    assert result.returncode == 2
    assert "sandbox name must contain only lowercase letters" in result.stderr


def test_cli_sbx_014_host_workspace_browser_json(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
    workspace_grant: str,
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        [
            "--workspace",
            workspace_grant,
            "--profile",
            "browser",
            "--json",
        ],
        sandbox_e2e_environment,
        expected_profile="browser",
        expected_workspace_id=workspace_grant,
        json_output=True,
    )


def test_cli_sbx_015_standalone_default_profile_json(
    mcpctl_executable: str,
    sandbox_name: str,
    sandbox_e2e_environment: dict[str, str],
) -> None:
    _create_and_verify(
        mcpctl_executable,
        sandbox_name,
        [
            "--standalone",
            "--profile",
            "default",
            "--json",
        ],
        sandbox_e2e_environment,
        expected_profile="default",
        expected_workspace_id=None,
        json_output=True,
    )


def test_cli_sbx_016_create_help(
    mcpctl_executable: str,
) -> None:
    result = _run_mcpctl(
        mcpctl_executable,
        ["sandbox", "create", "--help"],
    )

    assert result.returncode == 0
    assert "usage: mcpctl sandbox create" in result.stdout
    assert "name" in result.stdout
    assert "--workspace" in result.stdout
    assert "--standalone" in result.stdout
    assert "--profile" in result.stdout
    assert "default" in result.stdout
    assert "browser" in result.stdout
    assert "--json" in result.stdout
