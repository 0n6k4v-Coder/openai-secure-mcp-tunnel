from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


mcpctl = importlib.import_module("local_mcp_server.cli.mcpctl")
config_service = importlib.import_module("local_mcp_server.config.service")
paths = importlib.import_module("local_mcp_server.config.paths")


def _patch_config_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    clients_root = config_root / "mcp-clients"
    openai_root = clients_root / "openai"

    monkeypatch.setattr(
        config_service,
        "CONFIG_ROOT",
        config_root,
    )
    monkeypatch.setattr(
        config_service,
        "MCP_CLIENTS_ROOT",
        clients_root,
    )
    monkeypatch.setattr(
        config_service,
        "OPENAI_ROOT",
        openai_root,
    )
    monkeypatch.setattr(
        config_service,
        "OPENAI_CONFIG_FILE",
        openai_root / "config.yaml",
    )
    monkeypatch.setattr(
        config_service,
        "OPENAI_API_KEY_FILE",
        openai_root / "credentials",
    )


def test_xdg_config_home_defaults_to_user_config_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "XDG_CONFIG_HOME",
        raising=False,
    )

    assert paths.xdg_config_home() == (Path.home() / ".config")


def test_xdg_config_home_uses_absolute_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_root = tmp_path / "custom-config"

    monkeypatch.setenv(
        "XDG_CONFIG_HOME",
        str(configured_root),
    )

    assert paths.xdg_config_home() == configured_root


def test_xdg_config_home_ignores_relative_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "XDG_CONFIG_HOME",
        "relative-config",
    )

    assert paths.xdg_config_home() == (Path.home() / ".config")


def test_configure_openai_writes_expected_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config_paths(
        tmp_path,
        monkeypatch,
    )

    config_service.configure_openai(
        "tunnel_0123456789abcdef0123456789abcdef",
        "sk-test-value",
    )

    assert config_service.OPENAI_CONFIG_FILE.read_text(
        encoding="utf-8",
    ) == (
        "config_version: 1\n"
        "control_plane:\n"
        "  base_url: https://api.openai.com\n"
        "  tunnel_id: "
        '"tunnel_0123456789abcdef0123456789abcdef"\n'
        "  api_key: file:/run/secrets/CONTROL_PLANE_API_KEY\n"
        "mcp:\n"
        "  server_urls:\n"
        "    - channel: main\n"
        "      url: http://mcp-server:8000/mcp\n"
    )

    assert (
        config_service.OPENAI_API_KEY_FILE.read_text(
            encoding="utf-8",
        )
        == "sk-test-value\n"
    )

    assert config_service.OPENAI_CONFIG_FILE.stat().st_mode & 0o777 == 0o600

    assert config_service.OPENAI_API_KEY_FILE.stat().st_mode & 0o777 == 0o600

    assert config_service.OPENAI_CONFIG_FILE.parent.stat().st_mode & 0o777 == 0o700

    assert config_service.CONFIG_ROOT.stat().st_mode & 0o777 == 0o700

    assert config_service.MCP_CLIENTS_ROOT.stat().st_mode & 0o777 == 0o700


def test_configure_openai_rejects_insecure_existing_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config_paths(
        tmp_path,
        monkeypatch,
    )

    config_service.CONFIG_ROOT.mkdir(
        parents=True,
        mode=0o700,
    )

    config_service.CONFIG_ROOT.chmod(0o755)

    with pytest.raises(
        config_service.ConfigError,
        match="must not be accessible",
    ):
        config_service.configure_openai(
            "tunnel_0123456789abcdef0123456789abcdef",
            "sk-test-value",
        )


def test_configure_openai_hides_api_key_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, str] = {}

    def fake_input(prompt: str) -> str:
        captured["tunnel_prompt"] = prompt

        return "tunnel_0123456789abcdef0123456789abcdef"

    def fake_getpass(prompt: str) -> str:
        captured["api_key_prompt"] = prompt

        return "sk-secret-value"

    monkeypatch.setattr(
        mcpctl,
        "input",
        fake_input,
    )
    monkeypatch.setattr(
        mcpctl.getpass,
        "getpass",
        fake_getpass,
    )
    monkeypatch.setattr(
        mcpctl,
        "configure_openai",
        lambda tunnel_id, api_key: captured.update(
            {
                "tunnel_id": tunnel_id,
                "api_key": api_key,
            }
        ),
    )

    assert mcpctl._configure_openai() == mcpctl.EXIT_OK

    output = capsys.readouterr().out

    assert "sk-secret-value" not in output

    assert captured["api_key_prompt"] == "CONTROL_PLANE_API_KEY: "


def test_configure_openai_rejects_invalid_tunnel_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config_paths(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(
        config_service.ConfigError,
        match="CONTROL_PLANE_TUNNEL_ID",
    ):
        config_service.configure_openai(
            "invalid",
            "sk-test-value",
        )


def test_configure_openai_rejects_empty_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config_paths(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(
        config_service.ConfigError,
        match="CONTROL_PLANE_API_KEY",
    ):
        config_service.configure_openai(
            "tunnel_0123456789abcdef0123456789abcdef",
            "",
        )


def test_mcp_client_setup_flow_shows_status_table_and_skip(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = mcpctl.lifecycle.get_mcp_client_statuses()[0]

    unconfigured_client = type(client)(
        key=client.key,
        display_name=client.display_name,
        required=client.required,
        configured=False,
        config_present=False,
        credentials_present=False,
        permissions_secure=None,
        config_file=client.config_file,
        credentials_file=client.credentials_file,
        insecure_paths=(),
    )

    monkeypatch.setattr(
        mcpctl.lifecycle,
        "get_mcp_client_statuses",
        lambda: (unconfigured_client,),
    )

    monkeypatch.setattr(
        mcpctl,
        "_prompt_choice",
        lambda title, options: 2,
    )

    assert (
        mcpctl._config_mcp_client(
            allow_skip=True,
        )
        == mcpctl.EXIT_OK
    )

    output = capsys.readouterr().out

    assert "MCP Clients" in output
    assert "CLIENT" in output
    assert "CONFIGURATION" in output
    assert "OpenAI" in output
    assert "○ NOT CONFIGURED" in output
    assert "MCP client configuration skipped." in output
    assert "You can configure it later with:" in output
    assert "mcpctl config mcp-client" in output
    assert "Configure OpenAI" not in output


def test_mcp_client_setup_configures_unconfigured_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = mcpctl.lifecycle.get_mcp_client_statuses()[0]

    unconfigured_client = type(client)(
        key=client.key,
        display_name=client.display_name,
        required=client.required,
        configured=False,
        config_present=False,
        credentials_present=False,
        permissions_secure=None,
        config_file=client.config_file,
        credentials_file=client.credentials_file,
        insecure_paths=(),
    )

    monkeypatch.setattr(
        mcpctl.lifecycle,
        "get_mcp_client_statuses",
        lambda: (unconfigured_client,),
    )

    called = False

    def fake_configure() -> int:
        nonlocal called
        called = True
        return mcpctl.EXIT_OK

    monkeypatch.setattr(
        mcpctl,
        "_prompt_choice",
        lambda title, options: 1,
    )
    monkeypatch.setattr(
        mcpctl,
        "_configure_openai",
        fake_configure,
    )

    assert (
        mcpctl._config_mcp_client(
            allow_skip=True,
        )
        == mcpctl.EXIT_OK
    )

    assert called is True


def test_mcp_client_setup_does_not_prompt_when_all_clients_configured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = mcpctl.lifecycle.get_mcp_client_statuses()[0]

    configured_client = type(client)(
        key=client.key,
        display_name=client.display_name,
        required=client.required,
        configured=True,
        config_present=True,
        credentials_present=True,
        permissions_secure=True,
        config_file=client.config_file,
        credentials_file=client.credentials_file,
        insecure_paths=(),
    )

    monkeypatch.setattr(
        mcpctl.lifecycle,
        "get_mcp_client_statuses",
        lambda: (configured_client,),
    )

    def fail_prompt(*args, **kwargs) -> int:
        raise AssertionError("configured MCP clients should not prompt")

    monkeypatch.setattr(
        mcpctl,
        "_prompt_choice",
        fail_prompt,
    )

    assert (
        mcpctl._config_mcp_client(
            allow_skip=True,
        )
        == mcpctl.EXIT_OK
    )

    output = capsys.readouterr().out

    assert "All MCP clients are configured." in output


def test_mcp_client_management_shows_configured_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = mcpctl.lifecycle.get_mcp_client_statuses()[0]

    configured_client = type(client)(
        key=client.key,
        display_name=client.display_name,
        required=client.required,
        configured=True,
        config_present=True,
        credentials_present=True,
        permissions_secure=True,
        config_file=client.config_file,
        credentials_file=client.credentials_file,
        insecure_paths=(),
        runtime="✓ ACTIVE",
    )

    monkeypatch.setattr(
        mcpctl.lifecycle,
        "get_mcp_client_statuses",
        lambda: (configured_client,),
    )

    calls: list[list[str]] = []

    def fake_prompt(
        title: str,
        options: list[str],
    ) -> int:
        calls.append(options)
        if title == "Choose MCP client":
            return 1
        return 2

    monkeypatch.setattr(
        mcpctl,
        "_prompt_choice",
        fake_prompt,
    )

    assert mcpctl._config_mcp_client() == mcpctl.EXIT_OK

    output = capsys.readouterr().out

    assert "✓ CONFIGURED" in output
    assert "✓ PRESENT" in output
    assert "✓ SECURE" in output
    assert "✓ ACTIVE" in output
    assert calls[0] == ["OpenAI"]
    assert calls[1] == ["Reconfigure", "Back"]


def test_mcp_client_management_configures_unconfigured_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = mcpctl.lifecycle.get_mcp_client_statuses()[0]

    unconfigured_client = type(client)(
        key=client.key,
        display_name=client.display_name,
        required=client.required,
        configured=False,
        config_present=False,
        credentials_present=False,
        permissions_secure=None,
        config_file=client.config_file,
        credentials_file=client.credentials_file,
        insecure_paths=(),
    )

    monkeypatch.setattr(
        mcpctl.lifecycle,
        "get_mcp_client_statuses",
        lambda: (unconfigured_client,),
    )

    calls: list[list[str]] = []
    configured = False

    def fake_prompt(
        title: str,
        options: list[str],
    ) -> int:
        calls.append(options)
        return 1

    def fake_configure() -> int:
        nonlocal configured
        configured = True
        return mcpctl.EXIT_OK

    monkeypatch.setattr(
        mcpctl,
        "_prompt_choice",
        fake_prompt,
    )
    monkeypatch.setattr(
        mcpctl,
        "_configure_openai",
        fake_configure,
    )

    assert mcpctl._config_mcp_client() == mcpctl.EXIT_OK

    assert configured is True
    assert calls[0] == ["OpenAI"]
    assert calls[1] == ["Configure", "Back"]


def test_mcp_client_config_command_supports_direct_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_configure() -> int:
        nonlocal called
        called = True
        return mcpctl.EXIT_OK

    monkeypatch.setattr(
        mcpctl,
        "_configure_openai",
        fake_configure,
    )

    assert (
        mcpctl.main(
            ["config", "mcp-client", "openai"],
        )
        == mcpctl.EXIT_OK
    )

    assert called is True


def test_mcp_client_setup_skip_does_not_configure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_configure() -> int:
        nonlocal called
        called = True
        return mcpctl.EXIT_OK

    monkeypatch.setattr(
        mcpctl,
        "_prompt_choice",
        lambda title, options: 2,
    )
    monkeypatch.setattr(
        mcpctl,
        "_configure_openai",
        fake_configure,
    )

    assert (
        mcpctl._config_mcp_client(
            allow_skip=True,
        )
        == mcpctl.EXIT_OK
    )

    assert called is False


def test_mcpctl_sandbox_create_parser_supports_standalone() -> None:
    parser = mcpctl._build_parser()

    args = parser.parse_args(
        [
            "sandbox",
            "create",
            "std-test",
            "--standalone",
        ]
    )

    assert args.workspace_id is None
    assert args.standalone is True
    assert args.profile == "default"

    assert mcpctl._sandbox_arguments(args) == [
        "create",
        "std-test",
        "--standalone",
        "--profile",
        "default",
    ]


def test_mcpctl_sandbox_create_parser_requires_workspace_source() -> None:
    parser = mcpctl._build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "sandbox",
                "create",
                "std-test",
            ]
        )


def test_mcpctl_sandbox_create_parser_preserves_host_workspace() -> None:
    parser = mcpctl._build_parser()

    args = parser.parse_args(
        [
            "sandbox",
            "create",
            "project-api",
            "--workspace",
            "ws_project",
            "--profile",
            "browser",
        ]
    )

    assert args.workspace_id == "ws_project"
    assert args.standalone is False
    assert mcpctl._sandbox_arguments(args) == [
        "create",
        "project-api",
        "--workspace",
        "ws_project",
        "--profile",
        "browser",
    ]


def test_mcpctl_parser_contains_expected_commands() -> None:
    parser = mcpctl._build_parser()

    action = next(action for action in parser._actions if action.dest == "command")

    assert set(action.choices) == {
        "start",
        "stop",
        "restart",
        "compose-status",
        "logs",
        "setup",
        "status",
        "repair",
        "sandbox",
        "credential",
        "workspace",
        "config",
        "cleanup",
        "uninstall",
    }


def test_setup_configures_mcp_client_before_starting_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    tls_status = SimpleNamespace(complete=True)
    final_status = object()

    monkeypatch.setattr(
        mcpctl.lifecycle,
        "prepare_runtime",
        lambda: events.append("prepare_runtime"),
    )
    monkeypatch.setattr(
        mcpctl,
        "setup_openshell_tls",
        lambda: events.append("setup_tls") or tls_status,
    )
    monkeypatch.setattr(
        mcpctl,
        "_config_mcp_client",
        lambda *, allow_skip: (
            events.append(f"config_mcp_client:{allow_skip}") or mcpctl.EXIT_OK
        ),
    )
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "validate_compose",
        lambda: events.append("validate_compose"),
    )
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "start_core_services",
        lambda: events.append("start_core_services"),
    )
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "reconcile_tunnel_client",
        lambda: events.append("reconcile_tunnel_client"),
    )
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "verify",
        lambda status: (
            events.append(f"verify:{status is tls_status}") or final_status
        ),
    )
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "get_status",
        lambda status: type(
            "Status",
            (),
            {
                "tunnel_client": type(
                    "Service",
                    (),
                    {"running": False},
                )(),
                "mcp_clients": (),
            },
        )(),
    )
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "print_status",
        lambda status: events.append(f"print_status:{status is final_status}"),
    )

    assert mcpctl._setup() == mcpctl.EXIT_OK

    assert events == [
        "prepare_runtime",
        "setup_tls",
        "config_mcp_client:True",
        "validate_compose",
        "start_core_services",
        "reconcile_tunnel_client",
        "verify:True",
        "print_status:True",
    ]


@pytest.mark.parametrize(
    ("argv", "expected_command", "expected_arguments"),
    [
        (["start"], "start", []),
        (["stop"], "stop", []),
        (["restart"], "restart", []),
        (["compose-status"], "status", []),
        (["compose-status", "--json"], "status", ["--json"]),
        (["logs"], "logs", ["--tail", "100"]),
        (
            ["logs", "mcp-server", "--follow", "--tail", "25"],
            "logs",
            ["mcp-server", "--follow", "--tail", "25"],
        ),
    ],
)
def test_compose_commands_delegate_to_shared_cli(
    argv: list[str],
    expected_command: str,
    expected_arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_delegate(command: str, arguments: list[str]) -> int:
        captured["command"] = command
        captured["arguments"] = arguments
        return 17

    monkeypatch.setattr(mcpctl, "_delegate_local_cli", fake_delegate)

    assert mcpctl.main(argv) == 17
    assert captured == {
        "command": expected_command,
        "arguments": expected_arguments,
    }


def test_cleanup_is_read_only_and_reports_legacy_profile_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    profile = config_home / "local-mcp-server/profiles/dev"
    profile.mkdir(parents=True)
    (profile / "profile.json").write_text("{}", encoding="utf-8")
    state_profile = state_home / "local-mcp-server/profiles/dev"
    state_profile.mkdir(parents=True)

    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: config_home)
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: state_home)

    assert mcpctl.main(["cleanup"]) == mcpctl.EXIT_OK
    output = capsys.readouterr().out
    assert str(profile) in output
    assert "No files" in output
    assert (profile / "profile.json").is_file()
    assert state_profile.is_dir()


def test_uninstall_defaults_to_dry_run_and_preserves_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    profile = config_home / "local-mcp-server/profiles/dev"
    profile.mkdir(parents=True)
    (profile / "profile.json").write_text("{}", encoding="utf-8")
    state_profile = state_home / "local-mcp-server/profiles/dev"
    state_profile.mkdir(parents=True)

    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: config_home)
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: state_home)

    assert mcpctl.main(["uninstall"]) == mcpctl.EXIT_OK
    assert "Dry run only" in capsys.readouterr().out
    assert profile.is_dir()
    assert state_profile.is_dir()


def test_uninstall_yes_removes_only_marked_profile_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    profile = config_home / "local-mcp-server/profiles/dev"
    profile.mkdir(parents=True)
    (profile / "profile.json").write_text("{}", encoding="utf-8")
    unrelated = config_home / "local-mcp-server/profiles/unrelated"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep", encoding="utf-8")
    state_profile = state_home / "local-mcp-server/profiles/dev"
    state_profile.mkdir(parents=True)
    (state_profile / "state.json").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: config_home)
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: state_home)

    assert mcpctl.main(["uninstall", "--yes"]) == mcpctl.EXIT_OK
    capsys.readouterr()
    assert not profile.exists()
    assert (unrelated / "keep.txt").is_file()
    assert (state_profile / "state.json").read_text(encoding="utf-8") == "keep"


def test_uninstall_purge_removes_app_config_and_state_but_preserves_external_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    app_config = config_home / "local-mcp-server"
    app_state = state_home / "local-mcp-server"
    credentials = app_config / "mcp-clients/openai/credentials"
    workspace_grants = app_state / "mcp/workspace-grants/workspace-grants.json"
    credentials.parent.mkdir(parents=True)
    workspace_grants.parent.mkdir(parents=True)
    credentials.write_text("secret", encoding="utf-8")
    workspace_grants.write_text("{}", encoding="utf-8")
    host_workspace = tmp_path / "host-workspace"
    host_workspace.mkdir()
    (host_workspace / "keep.txt").write_text("keep", encoding="utf-8")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "README.md").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: config_home)
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: state_home)
    monkeypatch.setattr(mcpctl.shutil, "which", lambda _: None)

    assert mcpctl.main(["uninstall", "--purge"]) == mcpctl.EXIT_OK
    assert "Dry run only" in capsys.readouterr().out
    assert credentials.is_file()
    assert workspace_grants.is_file()

    assert mcpctl.main(["uninstall", "--yes", "--purge"]) == mcpctl.EXIT_OK
    output = capsys.readouterr().out
    assert "Preserved host workspaces, Docker volumes, and the repository." in output
    assert not app_config.exists()
    assert not app_state.exists()
    assert (host_workspace / "keep.txt").is_file()
    assert (repository / "README.md").is_file()


def test_cleanup_json_reports_non_destructive_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: tmp_path / "config")
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: tmp_path / "state")

    assert mcpctl.main(["cleanup", "--json"]) == mcpctl.EXIT_OK
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["destructive"] is False
    assert payload["state_preserved"] is True
    assert payload["workspace_grants_preserved"] is True


def test_uninstall_purge_inventory_lists_client_files_and_preserves_external_mtls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    app_config = config_home / "local-mcp-server"
    app_state = state_home / "local-mcp-server"
    credentials = app_config / "mcp-clients/openai/credentials"
    config_file = app_config / "mcp-clients/openai/config.yaml"
    credentials.parent.mkdir(parents=True)
    credentials.write_text("never print this secret", encoding="utf-8")
    config_file.write_text("config_version: 1", encoding="utf-8")
    app_state.mkdir(parents=True)
    external_mtls = config_home / "openshell/gateways/local/mtls/tls.key"
    external_mtls.parent.mkdir(parents=True)
    external_mtls.write_text("preserve me", encoding="utf-8")

    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: config_home)
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: state_home)
    monkeypatch.setattr(mcpctl.shutil, "which", lambda _: None)

    assert mcpctl.main(["uninstall", "--purge"]) == mcpctl.EXIT_OK
    output = capsys.readouterr().out
    assert "OpenAI MCP config" in output
    assert "OpenAI MCP credentials (secret contents hidden)" in output
    assert "OUTSIDE SCOPE" in output
    assert str(external_mtls.parent) in output
    assert "never print this secret" not in output
    assert credentials.is_file()
    assert external_mtls.is_file()


def test_uninstall_purge_blocks_when_compose_services_are_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app_config = tmp_path / "config/local-mcp-server"
    app_state = tmp_path / "state/local-mcp-server"
    app_config.mkdir(parents=True)
    app_state.mkdir(parents=True)
    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: tmp_path / "config")
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: tmp_path / "state")
    monkeypatch.setattr(mcpctl.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "_service_statuses",
        lambda: {"mcp-server": SimpleNamespace(running=True)},
    )

    assert mcpctl.main(["uninstall", "--yes", "--purge"]) == mcpctl.EXIT_ERROR
    output = capsys.readouterr()
    assert "PREFLIGHT FAILED" in output.err
    assert "mcpctl stop" in output.err
    assert app_config.is_dir()
    assert app_state.is_dir()


def test_uninstall_purge_reports_partial_failure_and_verifies_successful_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    app_config = config_home / "local-mcp-server"
    app_state = state_home / "local-mcp-server"
    app_config.mkdir(parents=True)
    app_state.mkdir(parents=True)
    monkeypatch.setattr(mcpctl, "xdg_config_home", lambda: config_home)
    monkeypatch.setattr(mcpctl, "xdg_state_home", lambda: state_home)
    monkeypatch.setattr(mcpctl.shutil, "which", lambda _: None)
    real_rmtree = mcpctl.shutil.rmtree

    def fail_state_root(path: Path, *args: object, **kwargs: object) -> None:
        if Path(path) == app_state:
            raise PermissionError("test permission failure")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(mcpctl.shutil, "rmtree", fail_state_root)
    assert mcpctl.main(["uninstall", "--yes", "--purge"]) == mcpctl.EXIT_ERROR
    output = capsys.readouterr()
    assert "REMOVED (verified absent)" in output.out
    assert "PARTIAL FAILURE" in output.err
    assert not app_config.exists()
    assert app_state.is_dir()
