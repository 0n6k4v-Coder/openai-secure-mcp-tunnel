from __future__ import annotations

from pathlib import Path

import pytest

from local_mcp_server.cli import workspace_broker
from local_mcp_server.config import paths


def test_default_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert paths.xdg_config_home() == Path.home() / ".config"


def test_default_xdg_state_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    assert paths.xdg_state_home() == Path.home() / ".local" / "state"


def test_absolute_xdg_overrides_are_used(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"

    monkeypatch.setenv(
        "XDG_CONFIG_HOME",
        str(config_home),
    )
    monkeypatch.setenv(
        "XDG_STATE_HOME",
        str(state_home),
    )

    assert paths.xdg_config_home() == config_home
    assert paths.xdg_state_home() == state_home


def test_relative_xdg_overrides_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "XDG_CONFIG_HOME",
        "relative-config",
    )
    monkeypatch.setenv(
        "XDG_STATE_HOME",
        "relative-state",
    )

    assert paths.xdg_config_home() == Path.home() / ".config"
    assert paths.xdg_state_home() == Path.home() / ".local" / "state"


def test_application_paths_are_canonical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"

    monkeypatch.setenv(
        "XDG_CONFIG_HOME",
        str(config_home),
    )
    monkeypatch.setenv(
        "XDG_STATE_HOME",
        str(state_home),
    )

    assert paths.app_config_root() == (config_home / "local-mcp-server")
    assert paths.app_state_root() == (state_home / "local-mcp-server")
    assert paths.openai_config_file() == (
        config_home / "local-mcp-server" / "mcp-clients" / "openai" / "config.yaml"
    )
    assert paths.openai_api_key_file() == (
        config_home / "local-mcp-server" / "mcp-clients" / "openai" / "credentials"
    )
    assert paths.installation_state_file() == (
        state_home / "local-mcp-server" / "mcp" / "installations.json"
    )
    assert paths.workspace_grants_file() == (
        state_home
        / "local-mcp-server"
        / "mcp"
        / "workspace-grants"
        / "workspace-grants.json"
    )


def test_workspace_broker_protects_canonical_application_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()

    config_root = home / ".config" / "local-mcp-server"
    state_root = home / ".local" / "state" / "local-mcp-server"

    monkeypatch.setattr(
        workspace_broker,
        "app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        workspace_broker,
        "app_state_root",
        lambda: state_root,
    )

    assert workspace_broker._is_protected_path(
        config_root / "mcp-clients" / "openai" / "credentials",
        home,
    )

    assert workspace_broker._is_protected_path(
        state_root / "mcp" / "installations.json",
        home,
    )

    assert not workspace_broker._is_protected_path(
        home / "projects" / "example" / "README.md",
        home,
    )


def test_workspace_broker_rejects_unsafe_canonical_state_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()

    config_root = home / ".config" / "local-mcp-server"
    state_root = home / ".local" / "state" / "local-mcp-server"

    config_root.mkdir(parents=True)
    state_root.mkdir(parents=True)

    config_root.chmod(0o700)
    state_root.chmod(0o755)

    monkeypatch.setattr(
        workspace_broker,
        "app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        workspace_broker,
        "app_state_root",
        lambda: state_root,
    )

    with pytest.raises(
        RuntimeError,
        match="unsafe permissions",
    ):
        workspace_broker._validate_protected_path_permissions(home)
