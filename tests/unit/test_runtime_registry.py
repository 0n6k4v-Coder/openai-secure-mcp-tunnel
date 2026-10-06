from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_mcp_server.runtime.registry import (
    RuntimeRegistryError,
    create_runtime,
    delete_runtime,
    list_runtimes,
    load_runtime,
)


def test_default_runtime_is_always_available(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert [profile.name for profile in list_runtimes()] == ["default"]
    assert load_runtime("default").openshell_workspace == "default"


def test_create_load_and_delete_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    created = create_runtime("integration", "test runtime")
    assert created == load_runtime("integration")
    assert [profile.name for profile in list_runtimes()] == ["default", "integration"]
    registry = tmp_path / "local-mcp-server" / "runtimes.json"
    assert registry.stat().st_mode & 0o777 == 0o600
    delete_runtime("integration")
    assert [profile.name for profile in list_runtimes()] == ["default"]


@pytest.mark.parametrize("name", ["../escape", "Uppercase", "two words", "-bad", "default"])
def test_invalid_or_reserved_runtime_name_is_rejected(
    monkeypatch, tmp_path: Path, name: str
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(RuntimeRegistryError):
        create_runtime(name)


def test_registry_symlink_is_rejected(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    root = tmp_path / "local-mcp-server"
    root.mkdir()
    target = tmp_path / "other.json"
    target.write_text(json.dumps({"schema_version": 1, "runtimes": []}))
    (root / "runtimes.json").symlink_to(target)
    with pytest.raises(RuntimeRegistryError, match="symlink"):
        list_runtimes()
