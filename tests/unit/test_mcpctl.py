from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


mcpctl = importlib.import_module(
    "local_mcp_server.cli.mcpctl"
)
config_service = importlib.import_module(
    "local_mcp_server.config.service"
)
paths = importlib.import_module(
    "local_mcp_server.config.paths"
)


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

    assert paths.xdg_config_home() == (
        Path.home() / ".config"
    )


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

    assert paths.xdg_config_home() == (
        Path.home() / ".config"
    )


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
        "\"tunnel_0123456789abcdef0123456789abcdef\"\n"
        "  api_key: file:/run/secrets/CONTROL_PLANE_API_KEY\n"
        "mcp:\n"
        "  server_urls:\n"
        "    - channel: main\n"
        "      url: http://mcp-server:8000/mcp\n"
    )

    assert config_service.OPENAI_API_KEY_FILE.read_text(
        encoding="utf-8",
    ) == "sk-test-value\n"

    assert (
        config_service.OPENAI_CONFIG_FILE.stat().st_mode
        & 0o777
        == 0o600
    )

    assert (
        config_service.OPENAI_API_KEY_FILE.stat().st_mode
        & 0o777
        == 0o600
    )

    assert (
        config_service.OPENAI_CONFIG_FILE.parent.stat().st_mode
        & 0o777
        == 0o700
    )

    assert (
        config_service.CONFIG_ROOT.stat().st_mode
        & 0o777
        == 0o700
    )

    assert (
        config_service.MCP_CLIENTS_ROOT.stat().st_mode
        & 0o777
        == 0o700
    )


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

    config_service.CONFIG_ROOT.chmod(
        0o755
    )

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

        return (
            "tunnel_0123456789abcdef0123456789abcdef"
        )

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

    assert (
        mcpctl._configure_openai()
        == mcpctl.EXIT_OK
    )

    output = capsys.readouterr().out

    assert "sk-secret-value" not in output

    assert (
        captured["api_key_prompt"]
        == "CONTROL_PLANE_API_KEY: "
    )


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
    client = (
        mcpctl.lifecycle.get_mcp_client_statuses()[0]
    )

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
        raise AssertionError(
            "configured MCP clients should not prompt"
        )

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

    assert (
        mcpctl._config_mcp_client()
        == mcpctl.EXIT_OK
    )

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
    client = (
        mcpctl.lifecycle.get_mcp_client_statuses()[0]
    )

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

    assert (
        mcpctl._config_mcp_client()
        == mcpctl.EXIT_OK
    )

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


def test_mcpctl_parser_contains_expected_commands() -> None:
    parser = mcpctl._build_parser()

    action = next(
        action
        for action in parser._actions
        if action.dest == "command"
    )

    assert set(action.choices) == {
        "setup",
        "status",
        "repair",
        "sandbox",
        "credential",
        "workspace",
        "config",
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
            events.append(
                f"config_mcp_client:{allow_skip}"
            )
            or mcpctl.EXIT_OK
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
        lambda: events.append(
            "reconcile_tunnel_client"
        ),
    )
    monkeypatch.setattr(
        mcpctl.lifecycle,
        "verify",
        lambda status: (
            events.append(
                f"verify:{status is tls_status}"
            )
            or final_status
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
        lambda status: events.append(
            f"print_status:{status is final_status}"
        ),
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