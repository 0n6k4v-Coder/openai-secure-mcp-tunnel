from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_mcp_server.cli import profiles


def _configure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profiles, "xdg_config_home", lambda: tmp_path / "config")
    monkeypatch.setattr(profiles, "xdg_state_home", lambda: tmp_path / "state")
    monkeypatch.setattr(profiles, "_repository_root", lambda: Path(__file__).parents[2])
    monkeypatch.setattr(
        profiles, "_allocate_ports",
        lambda: {"gateway": 18080, "health": 18081, "mcp": 18082},
    )


def test_profile_name_validation() -> None:
    assert profiles._validate_name("dev-1") == "dev-1"
    for name in ("", "../dev", "Dev", "has space", "a" * 32):
        with pytest.raises(profiles.ProfileError):
            profiles._validate_name(name)


def test_create_profile_isolates_config_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_paths(tmp_path, monkeypatch)
    manifest = profiles.create_profile("dev")
    root = tmp_path / "config/local-mcp-server/profiles/dev"
    assert manifest["project_name"] == "mcp-dev"
    assert json.loads((root / "profile.json").read_text()) == manifest
    assert (root / "deploy/gateway.toml").is_file()
    assert (root / "deploy/gateway-metadata.json").is_file()
    assert (tmp_path / "state/local-mcp-server/profiles/dev/xdg-state").is_dir()
    assert profiles.validate_profile("dev") == []


def test_create_profile_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_paths(tmp_path, monkeypatch)
    profiles.create_profile("dev")
    with pytest.raises(profiles.ProfileError, match="already exists"):
        profiles.create_profile("dev")


def test_profile_environment_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_paths(tmp_path, monkeypatch)
    profiles.create_profile("dev")
    env = profiles._profile_environment("dev")
    assert env["COMPOSE_PROJECT_NAME"] == "mcp-dev"
    assert env["OPENSHELL_PORT"] == "18080"
    assert env["OPENSHELL_HEALTH_PORT"] == "18081"
    assert env["MCP_PORT"] == "18082"
    assert env["OPENSHELL_CLI_GATEWAY"] == "https://openshell-gateway:8080"
    assert env["XDG_CONFIG_HOME"] != env["XDG_STATE_HOME"]
