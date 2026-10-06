from __future__ import annotations

from pathlib import Path

import pytest

from local_mcp_server.runtime.context import get_runtime_context
from local_mcp_server.runtime.registry import create_runtime


def test_default_context_preserves_legacy_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("MCP_RUNTIME", raising=False)
    context = get_runtime_context()
    assert context.is_default
    assert context.config_root == tmp_path / "config" / "local-mcp-server"
    assert context.state_root == tmp_path / "state" / "local-mcp-server"


def test_named_runtime_gets_separate_roots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    create_runtime("staging")
    monkeypatch.setenv("MCP_RUNTIME", "staging")
    context = get_runtime_context()
    assert context.config_root == tmp_path / "config" / "local-mcp-server" / "runtimes" / "staging"
    assert context.state_root == tmp_path / "state" / "local-mcp-server" / "runtimes" / "staging"
    assert context.profile.openshell_workspace == "mcp-staging"


def test_child_environment_scopes_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    create_runtime("qa")
    context = get_runtime_context("qa")
    child = context.child_environment({})
    assert child["MCP_RUNTIME"] == "qa"
    assert child["OPENSHELL_WORKSPACE"] == "mcp-qa"
    assert child["COMPOSE_PROJECT_NAME"].endswith("-qa")


def test_unknown_runtime_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("MCP_RUNTIME", "missing")
    with pytest.raises(RuntimeError, match="not registered"):
        get_runtime_context()


def test_named_runtime_selects_its_own_cli_gateway(monkeypatch, tmp_path: Path) -> None:
    from local_mcp_server.infrastructure.openshell.credentials import _gateway_endpoint

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("OPENSHELL_CLI_GATEWAY", raising=False)
    monkeypatch.delenv("OPENSHELL_RUNTIME_GATEWAY", raising=False)
    create_runtime("gateway-check")
    monkeypatch.setenv("MCP_RUNTIME", "gateway-check")
    profile = get_runtime_context().profile
    assert _gateway_endpoint() == f"https://127.0.0.1:{profile.openshell_port}"

def test_default_credential_commands_use_registered_local_gateway(
    monkeypatch, tmp_path: Path
) -> None:
    from local_mcp_server.infrastructure.openshell import credentials

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("MCP_RUNTIME", raising=False)
    monkeypatch.delenv("OPENSHELL_CLI_GATEWAY", raising=False)
    monkeypatch.setattr(credentials, "_command_exists", lambda _command: None)

    assert credentials._openshell_command("provider", "list") == [
        "openshell",
        "--gateway",
        "local",
        "provider",
        "list",
    ]


def test_explicit_credential_endpoint_override_is_preserved(
    monkeypatch, tmp_path: Path
) -> None:
    from local_mcp_server.infrastructure.openshell import credentials

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("MCP_RUNTIME", raising=False)
    monkeypatch.setenv("OPENSHELL_CLI_GATEWAY", "https://127.0.0.1:9443")
    monkeypatch.setattr(credentials, "_command_exists", lambda _command: None)

    assert credentials._openshell_command("provider", "list") == [
        "openshell",
        "--gateway-endpoint",
        "https://127.0.0.1:9443",
        "provider",
        "list",
    ]

