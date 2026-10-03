from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_mcp_server.cli import lifecycle


def test_prepare_runtime_creates_canonical_runtime_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config" / "local-mcp-server"
    state_root = tmp_path / "state" / "local-mcp-server"

    monkeypatch.setattr(
        lifecycle,
        "app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        lifecycle,
        "app_state_root",
        lambda: state_root,
    )
    monkeypatch.setattr(
        lifecycle,
        "installation_state_file",
        lambda: state_root
        / "mcp"
        / "installations.json",
    )
    monkeypatch.setattr(
        lifecycle,
        "workspace_grants_file",
        lambda: state_root
        / "mcp"
        / "workspace-grants"
        / "workspace-grants.json",
    )

    lifecycle.prepare_runtime()

    assert config_root.is_dir()
    assert state_root.is_dir()

    assert (
        state_root
        / "config"
        / "credentials"
    ).is_dir()

    assert (
        state_root
        / "openshell"
        / "tls"
    ).is_dir()

    assert (
        state_root
        / "mcp"
        / "workspace-grants"
    ).is_dir()

    assert (
        state_root
        / "logs"
    ).is_dir()

    installation_file = (
        state_root
        / "mcp"
        / "installations.json"
    )

    grants_file = (
        state_root
        / "mcp"
        / "workspace-grants"
        / "workspace-grants.json"
    )

    assert json.loads(
        installation_file.read_text(
            encoding="utf-8",
        )
    ) == {}

    assert json.loads(
        grants_file.read_text(
            encoding="utf-8",
        )
    ) == {}

    assert (
        installation_file.stat().st_mode
        & 0o777
        == 0o600
    )

    assert (
        grants_file.stat().st_mode
        & 0o777
        == 0o600
    )


def test_prepare_runtime_rejects_insecure_state_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    state_root = tmp_path / "state"

    config_root.mkdir()
    state_root.mkdir()

    state_root.chmod(0o755)

    monkeypatch.setattr(
        lifecycle,
        "app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        lifecycle,
        "app_state_root",
        lambda: state_root,
    )
    monkeypatch.setattr(
        lifecycle,
        "installation_state_file",
        lambda: state_root
        / "mcp"
        / "installations.json",
    )
    monkeypatch.setattr(
        lifecycle,
        "workspace_grants_file",
        lambda: state_root
        / "mcp"
        / "workspace-grants"
        / "workspace-grants.json",
    )

    with pytest.raises(
        lifecycle.LifecycleError,
        match="must not be accessible",
    ):
        lifecycle.prepare_runtime()


def test_mcp_client_is_not_configured_when_files_are_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    clients_root = config_root / "mcp-clients"
    openai_root = clients_root / "openai"

    monkeypatch.setattr(
        lifecycle,
        "app_config_root",
        lambda: config_root,
    )

    import local_mcp_server.config.paths as paths

    monkeypatch.setattr(
        paths,
        "app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        paths,
        "mcp_clients_root",
        lambda: clients_root,
    )
    monkeypatch.setattr(
        paths,
        "openai_root",
        lambda: openai_root,
    )
    monkeypatch.setattr(
        paths,
        "openai_config_file",
        lambda: openai_root / "config.yaml",
    )
    monkeypatch.setattr(
        paths,
        "openai_api_key_file",
        lambda: openai_root / "credentials",
    )

    status = lifecycle.get_mcp_client_status()

    assert status.configured is False


def test_mcp_client_is_configured_only_when_both_files_are_secure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    clients_root = config_root / "mcp-clients"
    openai_root = clients_root / "openai"

    openai_root.mkdir(parents=True)

    config_file = openai_root / "config.yaml"
    credentials_file = openai_root / "credentials"

    config_file.write_text(
        (
            "config_version: 1\n"
            "control_plane:\n"
            "  base_url: https://api.openai.com\n"
            "  tunnel_id: "
            "\"tunnel_0123456789abcdef0123456789abcdef\"\n"
            "  api_key: "
            "file:/run/secrets/CONTROL_PLANE_API_KEY\n"
            "mcp:\n"
            "  server_urls:\n"
            "    - channel: main\n"
            "      url: http://mcp-server:8000/mcp\n"
        ),
        encoding="utf-8",
    )

    credentials_file.write_text(
        "sk-test-value\n",
        encoding="utf-8",
    )

    for path in (
        config_root,
        clients_root,
        openai_root,
    ):
        path.chmod(0o700)

    config_file.chmod(0o600)
    credentials_file.chmod(0o600)

    import local_mcp_server.config.paths as paths

    monkeypatch.setattr(
        paths,
        "app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        paths,
        "mcp_clients_root",
        lambda: clients_root,
    )
    monkeypatch.setattr(
        paths,
        "openai_root",
        lambda: openai_root,
    )
    monkeypatch.setattr(
        paths,
        "openai_config_file",
        lambda: config_file,
    )
    monkeypatch.setattr(
        paths,
        "openai_api_key_file",
        lambda: credentials_file,
    )

    status = lifecycle.get_mcp_client_status()

    assert status.configured is True
    assert status.insecure_paths == ()


def test_mcp_client_is_not_configured_with_insecure_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    clients_root = config_root / "mcp-clients"
    openai_root = clients_root / "openai"

    openai_root.mkdir(parents=True)

    config_file = openai_root / "config.yaml"
    credentials_file = openai_root / "credentials"

    config_file.write_text(
        "config_version: 1\n",
        encoding="utf-8",
    )
    credentials_file.write_text(
        "sk-test-value\n",
        encoding="utf-8",
    )

    config_root.chmod(0o700)
    clients_root.chmod(0o700)
    openai_root.chmod(0o700)
    config_file.chmod(0o644)
    credentials_file.chmod(0o600)

    import local_mcp_server.config.paths as paths

    monkeypatch.setattr(
        paths,
        "app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        paths,
        "mcp_clients_root",
        lambda: clients_root,
    )
    monkeypatch.setattr(
        paths,
        "openai_root",
        lambda: openai_root,
    )
    monkeypatch.setattr(
        paths,
        "openai_config_file",
        lambda: config_file,
    )
    monkeypatch.setattr(
        paths,
        "openai_api_key_file",
        lambda: credentials_file,
    )

    status = lifecycle.get_mcp_client_status()

    assert status.configured is False
    assert config_file in status.insecure_paths


def test_reconcile_tunnel_removes_container_when_client_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        lifecycle,
        "get_mcp_client_status",
        lambda: lifecycle.MCPClientStatus(
            configured=False,
            config_file=Path("/tmp/config.yaml"),
            credentials_file=Path("/tmp/credentials"),
            insecure_paths=(),
        ),
    )

    monkeypatch.setattr(
        lifecycle,
        "remove_tunnel_client",
        lambda: calls.append("remove"),
    )

    monkeypatch.setattr(
        lifecycle,
        "start_tunnel_client",
        lambda: calls.append("start"),
    )

    lifecycle.reconcile_tunnel_client()

    assert calls == ["remove"]


def test_reconcile_tunnel_starts_when_client_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        lifecycle,
        "get_mcp_client_status",
        lambda: lifecycle.MCPClientStatus(
            configured=True,
            config_file=Path("/tmp/config.yaml"),
            credentials_file=Path("/tmp/credentials"),
            insecure_paths=(),
        ),
    )

    monkeypatch.setattr(
        lifecycle,
        "remove_tunnel_client",
        lambda: calls.append("remove"),
    )

    monkeypatch.setattr(
        lifecycle,
        "start_tunnel_client",
        lambda: calls.append("start"),
    )

    lifecycle.reconcile_tunnel_client()

    assert calls == ["start"]