from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_mcp_server.packages import manager


def test_registry_exposes_registered_ecosystem() -> None:
    assert manager.registered_ecosystems() == ("npm",)
    assert manager.get_adapter("npm").manifest_name == "package.json"


def test_unregistered_ecosystem_is_rejected() -> None:
    with pytest.raises(manager.PackageManagerError, match="not registered"):
        manager.get_adapter("python")


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("requests", ("requests", "*")),
        ("express@^5.0.0", ("express", "^5.0.0")),
        ("@scope/package@~2.1", ("@scope/package", "~2.1")),
    ],
)
def test_npm_adapter_validates_package_specs(spec: str, expected: tuple[str, str]) -> None:
    assert manager.get_adapter("npm").validate_spec(spec) == expected


@pytest.mark.parametrize("spec", ["../escape", "file:../local", "https://example.test/pkg.tgz", "git+https://example.test/pkg.git", "express@"])
def test_npm_adapter_rejects_unsafe_package_specs(spec: str) -> None:
    with pytest.raises(ValueError):
        manager.get_adapter("npm").validate_spec(spec)


def test_initialize_add_remove_and_reset_only_change_selected_ecosystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / "mcp-state"
    monkeypatch.setenv("MCP_STATE_DIR", str(state))
    initialized = manager.initialize_sandbox_packages("sandbox-one", "npm")
    assert initialized.manifest == state / "sandboxes/sandbox-one/packages/npm/package.json"
    assert json.loads(initialized.manifest.read_text())["dependencies"] == {}

    added = manager.add_package("sandbox-one", "npm", "express@^5.0.0")
    assert added.status == "configured"
    assert json.loads(added.manifest.read_text())["dependencies"] == {"express": "^5.0.0"}
    assert "OUT OF DATE" in added.message

    other = manager.initialize_sandbox_packages("sandbox-two", "npm")
    assert json.loads(other.manifest.read_text())["dependencies"] == {}

    removed = manager.remove_package("sandbox-one", "npm", "express")
    assert json.loads(removed.manifest.read_text())["dependencies"] == {}

    reset = manager.reset_packages("sandbox-one", "npm", confirmed=True)
    assert json.loads(reset.manifest.read_text())["dependencies"] == {}
    assert reset.status == "configured"


def test_add_rejects_duplicate_and_remove_rejects_missing_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    manager.initialize_sandbox_packages("sandbox-one", "npm")
    manager.add_package("sandbox-one", "npm", "express")
    with pytest.raises(manager.PackageManagerError, match="already configured"):
        manager.add_package("sandbox-one", "npm", "express@^5")
    with pytest.raises(manager.PackageManagerError, match="not configured"):
        manager.remove_package("sandbox-one", "npm", "missing")


def test_list_distinguishes_configuration_from_installation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    manager.initialize_sandbox_packages("sandbox-one", "npm")
    manager.add_package("sandbox-one", "npm", "express@^5")
    payload = manager.list_packages("sandbox-one")
    assert payload["packages"][0]["package"] == "express"
    assert payload["packages"][0]["status"] == "configured"
    details = manager.show_packages("sandbox-one")
    assert details["ecosystems"][0]["installation_status"] == "UNKNOWN"
    assert details["ecosystems"][0]["lock_status"] == "OUT OF DATE"


def test_package_state_delete_preserves_by_default_and_purges_only_explicitly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("MCP_STATE_DIR", str(state))
    result = manager.initialize_sandbox_packages("sandbox-one", "npm")
    preserved = manager.delete_package_state("sandbox-one")
    assert preserved["package_state"] == "PRESERVED"
    assert result.manifest.is_file()
    purged = manager.delete_package_state("sandbox-one", purge=True)
    assert purged["removed"] is True
    assert not result.manifest.parent.exists()


def test_package_state_rejects_symlinked_ecosystem_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("MCP_STATE_DIR", str(state))
    external = tmp_path / "external"
    external.mkdir()
    root = state / "sandboxes/sandbox-one/packages"
    root.mkdir(parents=True)
    (root / "npm").symlink_to(external, target_is_directory=True)
    with pytest.raises(manager.PackageManagerError, match="escapes|outside|symlink"):
        manager.initialize_sandbox_packages("sandbox-one", "npm")



def test_mcpctl_package_commands_are_registered_and_list_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from local_mcp_server.cli.mcpctl import _build_parser, _sandbox_arguments, main

    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    parser = _build_parser()
    args = parser.parse_args(["sandbox", "create", "sandbox-one", "--standalone", "--packages", "npm"])
    assert args.package_ecosystem == "npm"
    assert _sandbox_arguments(args) == [
        "create", "sandbox-one", "--packages", "npm", "--standalone", "--profile", "default"
    ]

    manager.initialize_sandbox_packages("sandbox-one", "npm")
    manager.add_package("sandbox-one", "npm", "express@^5")
    assert main(["sandbox", "packages", "list", "sandbox-one", "--ecosystem", "npm"]) == 0
    output = capsys.readouterr().out
    assert "express" in output
    assert "configured" in output
    assert "Package configuration" not in output or "Package state" in output


def test_mcpctl_package_show_and_reset_require_safe_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from local_mcp_server.cli.mcpctl import main

    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    manager.initialize_sandbox_packages("sandbox-one", "npm")
    assert main(["sandbox", "packages", "show", "sandbox-one"]) == 0
    show_output = capsys.readouterr().out
    assert "ECOSYSTEM" in show_output
    assert "npm" in show_output

    assert main(["sandbox", "packages", "reset", "sandbox-one", "--ecosystem", "npm", "--no-input"]) == 2
    assert "requires confirmation" in capsys.readouterr().err
    assert manager._read_json(manager._manifest_path("sandbox-one", "npm"))["private"] is True


def test_mcpctl_package_lock_fails_actionably_without_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from local_mcp_server.cli.mcpctl import main

    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    assert main(["sandbox", "packages", "lock", "sandbox-one", "--ecosystem", "npm"]) == 3
    output = capsys.readouterr().err
    assert "Package configuration was not found" in output
    assert "ERROR:" in output



def test_adapter_conformance_for_registered_ecosystems() -> None:
    for ecosystem in manager.registered_ecosystems():
        adapter = manager.get_adapter(ecosystem)
        manifest = adapter.base_manifest("sandbox-one")
        assert adapter.validate_manifest(manifest) == manifest
        assert adapter.dependencies(manifest) == {}
        assert adapter.manifest_name
        assert adapter.lock_name
        assert adapter.runtime_argv
        assert adapter.install_relative_path


def test_npm_capability_validation_rejects_browser_profile_before_changes() -> None:
    with pytest.raises(manager.PackageManagerError, match="requires sandbox profile") as exc:
        manager.validate_sandbox_capabilities("sandbox-one", "npm", "browser")
    assert exc.value.exit_code == 4



@pytest.mark.parametrize(
    ("stdout", "return_code", "expected"),
    [
        ('{"dependencies": {}}', 1, "NOT INSTALLED"),
        ('{"dependencies": {"express": {"version": "5.0.0"}}}', 1, "PARTIAL"),
        ('{"dependencies": {"express": {"version": "5.0.0"}}}', 0, "INSTALLED"),
    ],
)
def test_installation_verification_reports_real_environment_status(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    return_code: int,
    expected: str,
) -> None:
    import local_mcp_server.infrastructure.openshell.sandbox as sandbox_adapter

    monkeypatch.setattr(manager, "_lock_status", lambda _sandbox, _ecosystem: "UP TO DATE")
    monkeypatch.setattr(sandbox_adapter, "sandbox_status", lambda _name: '{"profile": "default"}')
    monkeypatch.setattr(
        sandbox_adapter,
        "execute_sandbox_argv",
        lambda *_args, **_kwargs: {"stdout": stdout, "stderr": "", "return_code": return_code},
    )
    assert manager.verify_installation("sandbox-one", "npm") == expected



def test_package_purge_preserves_unregistered_ecosystem_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("MCP_STATE_DIR", str(state))
    manager.initialize_sandbox_packages("sandbox-one", "npm")
    unknown = state / "sandboxes/sandbox-one/packages/unregistered"
    unknown.mkdir(parents=True)
    (unknown / "keep.txt").write_text("preserve", encoding="utf-8")

    result = manager.delete_package_state("sandbox-one", purge=True)
    assert result["package_state"] == "PARTIALLY REMOVED"
    assert result["preserved_entries"] == ["unregistered"]
    assert not (state / "sandboxes/sandbox-one/packages/npm").exists()
    assert (unknown / "keep.txt").read_text(encoding="utf-8") == "preserve"
