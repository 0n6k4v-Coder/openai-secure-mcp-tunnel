from __future__ import annotations

from pathlib import Path

from local_mcp_server.config import paths
from local_mcp_server.runtime.registry import create_runtime


def test_configuration_and_state_paths_are_runtime_scoped(
    monkeypatch, tmp_path: Path
) -> None:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    create_runtime("alpha")
    create_runtime("beta")

    monkeypatch.setenv("MCP_RUNTIME", "alpha")
    alpha_config = paths.app_config_root()
    alpha_state = paths.app_state_root()
    monkeypatch.setenv("MCP_RUNTIME", "beta")
    beta_config = paths.app_config_root()
    beta_state = paths.app_state_root()

    assert alpha_config != beta_config
    assert alpha_state != beta_state
    assert alpha_config.name == beta_config.name == "alpha" or alpha_config.parent == beta_config.parent
    assert alpha_config.parts[-1] == "alpha"
    assert beta_config.parts[-1] == "beta"


def test_default_runtime_keeps_original_path_layout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("MCP_RUNTIME", raising=False)
    assert paths.app_config_root() == tmp_path / "config" / "local-mcp-server"
