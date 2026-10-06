from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from local_mcp_server.cli import lifecycle


def _patch_openai_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path, Path]:
    config_root = tmp_path / "config"
    clients_root = config_root / "mcp-clients"
    openai_root = clients_root / "openai"
    config_file = openai_root / "config.yaml"
    credentials_file = openai_root / "credentials"

    monkeypatch.setattr(
        "local_mcp_server.config.paths.app_config_root",
        lambda: config_root,
    )
    monkeypatch.setattr(
        "local_mcp_server.config.paths.mcp_clients_root",
        lambda: clients_root,
    )
    monkeypatch.setattr(
        "local_mcp_server.config.paths.openai_root",
        lambda: openai_root,
    )
    monkeypatch.setattr(
        "local_mcp_server.config.paths.openai_config_file",
        lambda: config_file,
    )
    monkeypatch.setattr(
        "local_mcp_server.config.paths.openai_api_key_file",
        lambda: credentials_file,
    )

    monkeypatch.setattr(
        lifecycle,
        "app_config_root",
        lambda: config_root,
    )

    return (
        config_root,
        clients_root,
        openai_root,
        config_file,
        credentials_file,
    )


def _write_valid_openai_configuration(
    config_file: Path,
    credentials_file: Path,
) -> None:
    config_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_file.write_text(
        (
            "config_version: 1\n"
            "control_plane:\n"
            "  base_url: https://api.openai.com\n"
            "  tunnel_id: "
            '"tunnel_0123456789abcdef0123456789abcdef"\n'
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

    config_file.chmod(0o600)
    credentials_file.chmod(0o600)


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
        "workspace_grants_file",
        lambda: state_root / "mcp" / "workspace-grants" / "workspace-grants.json",
    )

    lifecycle.prepare_runtime()

    assert config_root.is_dir()
    assert state_root.is_dir()

    assert (state_root / "config" / "credentials").is_dir()

    assert (state_root / "openshell" / "tls").is_dir()

    assert (state_root / "mcp" / "workspace-grants").is_dir()

    assert (state_root / "logs").is_dir()

    grants_file = state_root / "mcp" / "workspace-grants" / "workspace-grants.json"

    assert (
        json.loads(
            grants_file.read_text(
                encoding="utf-8",
            )
        )
        == {}
    )

    assert grants_file.stat().st_mode & 0o777 == 0o600


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
        "workspace_grants_file",
        lambda: state_root / "mcp" / "workspace-grants" / "workspace-grants.json",
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
    (
        config_root,
        clients_root,
        openai_root,
        config_file,
        credentials_file,
    ) = _patch_openai_paths(
        tmp_path,
        monkeypatch,
    )

    assert config_root == lifecycle.app_config_root()
    assert clients_root.name == "mcp-clients"
    assert openai_root.name == "openai"
    assert not config_file.exists()
    assert not credentials_file.exists()

    statuses = lifecycle.get_mcp_client_statuses()

    assert len(statuses) == 1
    assert statuses[0].key == "openai"
    assert statuses[0].display_name == "OpenAI"
    assert statuses[0].available is True
    assert statuses[0].configured is False
    assert statuses[0].config_present is False
    assert statuses[0].credentials_present is False
    assert statuses[0].permissions_secure is None


def test_mcp_client_is_configured_only_when_both_files_are_secure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        clients_root,
        openai_root,
        config_file,
        credentials_file,
    ) = _patch_openai_paths(
        tmp_path,
        monkeypatch,
    )

    openai_root.mkdir(parents=True)

    _write_valid_openai_configuration(
        config_file,
        credentials_file,
    )

    for path in (
        config_root,
        clients_root,
        openai_root,
    ):
        path.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.chmod(0o700)

    statuses = lifecycle.get_mcp_client_statuses()

    assert statuses[0].configured is True
    assert statuses[0].config_present is True
    assert statuses[0].credentials_present is True
    assert statuses[0].permissions_secure is True
    assert statuses[0].insecure_paths == ()


def test_mcp_client_is_not_configured_with_insecure_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        clients_root,
        openai_root,
        config_file,
        credentials_file,
    ) = _patch_openai_paths(
        tmp_path,
        monkeypatch,
    )

    openai_root.mkdir(parents=True)

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

    statuses = lifecycle.get_mcp_client_statuses()

    assert statuses[0].configured is False
    assert statuses[0].permissions_secure is False
    assert config_file in statuses[0].insecure_paths


def test_mcp_client_is_not_configured_with_invalid_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        clients_root,
        openai_root,
        config_file,
        credentials_file,
    ) = _patch_openai_paths(
        tmp_path,
        monkeypatch,
    )

    config_root.mkdir(parents=True)
    clients_root.mkdir(parents=True)
    openai_root.mkdir(parents=True)

    config_root.chmod(0o700)
    clients_root.chmod(0o700)
    openai_root.chmod(0o700)

    config_file.write_text(
        "config_version: 1\n",
        encoding="utf-8",
    )
    credentials_file.write_text(
        "sk-test-value\n",
        encoding="utf-8",
    )

    config_file.chmod(0o600)
    credentials_file.chmod(0o600)

    statuses = lifecycle.get_mcp_client_statuses()

    assert statuses[0].configured is False
    assert statuses[0].config_present is True
    assert statuses[0].credentials_present is True
    assert statuses[0].permissions_secure is True


def test_get_mcp_client_status_returns_openai_compatibility_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openai_paths(
        tmp_path,
        monkeypatch,
    )

    status = lifecycle.get_mcp_client_status()

    assert status.key == "openai"
    assert status.display_name == "OpenAI"
    assert status.configured is False


def test_reconcile_tunnel_removes_container_when_client_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        lifecycle,
        "get_mcp_client_status",
        lambda: lifecycle.MCPClientStatus(
            key="openai",
            display_name="OpenAI",
            required=True,
            configured=False,
            config_present=False,
            credentials_present=False,
            permissions_secure=None,
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
            key="openai",
            display_name="OpenAI",
            required=True,
            configured=True,
            config_present=True,
            credentials_present=True,
            permissions_secure=True,
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


def test_lifecycle_ready_requires_required_client_and_running_tunnel() -> None:
    tls = SimpleNamespace(complete=True)

    client = lifecycle.MCPClientStatus(
        key="openai",
        display_name="OpenAI",
        required=True,
        configured=True,
        config_present=True,
        credentials_present=True,
        permissions_secure=True,
        config_file=Path("/tmp/config.yaml"),
        credentials_file=Path("/tmp/credentials"),
        insecure_paths=(),
        runtime="✓ ACTIVE",
    )

    gateway = lifecycle.ServiceStatus(
        service="openshell-gateway",
        state="running",
        health="healthy",
    )

    mcp_server = lifecycle.ServiceStatus(
        service="mcp-server",
        state="running",
        health="healthy",
    )

    tunnel = lifecycle.ServiceStatus(
        service="tunnel-client",
        state="running",
        health="running",
    )

    status = lifecycle.LifecycleStatus(
        tls=tls,
        mcp_clients=(client,),
        gateway=gateway,
        mcp_server=mcp_server,
        tunnel_client=tunnel,
    )

    assert status.infrastructure_ready is True
    assert status.required_mcp_clients_configured is True
    assert status.ready is True


def test_lifecycle_not_ready_when_required_client_is_unconfigured() -> None:
    tls = SimpleNamespace(complete=True)

    client = lifecycle.MCPClientStatus(
        key="openai",
        display_name="OpenAI",
        required=True,
        configured=False,
        config_present=False,
        credentials_present=False,
        permissions_secure=None,
        config_file=Path("/tmp/config.yaml"),
        credentials_file=Path("/tmp/credentials"),
        insecure_paths=(),
    )

    gateway = lifecycle.ServiceStatus(
        service="openshell-gateway",
        state="running",
        health="healthy",
    )

    mcp_server = lifecycle.ServiceStatus(
        service="mcp-server",
        state="running",
        health="healthy",
    )

    tunnel = lifecycle.ServiceStatus(
        service="tunnel-client",
        state="not running",
        health="",
    )

    status = lifecycle.LifecycleStatus(
        tls=tls,
        mcp_clients=(client,),
        gateway=gateway,
        mcp_server=mcp_server,
        tunnel_client=tunnel,
    )

    assert status.infrastructure_ready is True
    assert status.required_mcp_clients_configured is False
    assert status.ready is False



def test_local_image_defaults_match_documented_custom_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_mcp_server.cli import lifecycle

    monkeypatch.delenv("SANDBOX_IMAGE", raising=False)
    monkeypatch.delenv("BROWSER_SANDBOX_IMAGE", raising=False)
    monkeypatch.delenv("WORKSPACE_ACL_HELPER_IMAGE", raising=False)
    monkeypatch.setattr(lifecycle, "PROJECT_ROOT", Path("/project"))
    monkeypatch.setattr(lifecycle, "_configured_image_value", lambda variable, default: default)

    specs = lifecycle._local_image_specs()

    assert [spec[1] for spec in specs] == [
        "local-mcp-openshell-sandbox:1.0.0",
        "local-mcp-browser-sandbox:1.0.0",
        "local-mcp-workspace-acl-helper:1.0.0",
    ]
    assert [spec[2].name for spec in specs] == [
        "openshell-sandbox",
        "browser-sandbox",
        "workspace-acl-helper",
    ]


def test_ensure_local_images_builds_missing_image_and_verifies_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace
    from local_mcp_server.cli import lifecycle

    monkeypatch.setattr(lifecycle.shutil, "which", lambda command: "/usr/bin/docker")
    monkeypatch.setattr(lifecycle, "_local_image_specs", lambda: (
        ("SANDBOX_IMAGE", "local-mcp-openshell-sandbox:1.0.0", tmp_path),
    ))
    calls: list[list[str]] = []
    inspected = False

    def fake_capture(command: list[str]) -> SimpleNamespace:
        nonlocal inspected
        calls.append(command)
        if command[:3] == ["docker", "info", "--format"]:
            return SimpleNamespace(returncode=0, stdout="27.0", stderr="")
        if command[:3] == ["docker", "image", "inspect"]:
            if not inspected:
                inspected = True
                return SimpleNamespace(returncode=1, stdout="", stderr="not found")
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        if command[:2] == ["docker", "build"]:
            return SimpleNamespace(returncode=0, stdout="built", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(lifecycle, "_run_capture", fake_capture)

    statuses = lifecycle.ensure_local_images()

    assert len(statuses) == 1 and statuses[0].available
    assert any(command[:2] == ["docker", "build"] for command in calls)
    assert calls[-1][:3] == ["docker", "image", "inspect"]


def test_ensure_local_images_surfaces_build_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace
    from local_mcp_server.cli import lifecycle

    monkeypatch.setattr(lifecycle.shutil, "which", lambda command: "/usr/bin/docker")
    monkeypatch.setattr(lifecycle, "_local_image_specs", lambda: (
        ("SANDBOX_IMAGE", "local-mcp-openshell-sandbox:1.0.0", tmp_path),
    ))
    monkeypatch.setattr(
        lifecycle,
        "_run_capture",
        lambda command: (
            SimpleNamespace(returncode=0, stdout="27.0", stderr="")
            if command[:2] == ["docker", "info"]
            else SimpleNamespace(returncode=1, stdout="", stderr="build error")
            if command[:2] == ["docker", "image"]
            else SimpleNamespace(returncode=1, stdout="", stderr="build error")
        ),
    )

    with pytest.raises(lifecycle.LifecycleError, match="Build failed.*build error"):
        lifecycle.ensure_local_images()
