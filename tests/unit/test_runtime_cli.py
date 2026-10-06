from __future__ import annotations

import json
from pathlib import Path

from local_mcp_server.cli.mcpctl import main


def test_runtime_create_list_show_delete(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert main(["runtime", "create", "preview", "--description", "preview env"]) == 0
    assert "preview" in capsys.readouterr().out
    assert main(["runtime", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert any(item["name"] == "preview" for item in listed)
    assert main(["runtime", "show", "preview", "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["runtime"]["name"] == "preview"
    assert main(["runtime", "delete", "preview"]) == 2
    capsys.readouterr()
    assert main(["runtime", "delete", "preview", "--yes"]) == 0
    assert "deleted" in capsys.readouterr().out.lower()


def test_runtime_create_rejects_path_traversal(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert main(["runtime", "create", "../outside"]) == 2
    assert "ERROR:" in capsys.readouterr().err
    assert not (tmp_path.parent / "outside").exists()



def test_runtime_show_without_name_reports_effective_package_state_root(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("MCP_STATE_DIR", raising=False)
    assert main(["runtime", "show", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime"]["name"] == "default"
    assert payload["package_state"]["effective_state_root"] == str(
        (tmp_path / "state" / "local-mcp-server" / "mcp").resolve()
    )


def test_runtime_show_rejects_relative_mcp_state_dir(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("MCP_STATE_DIR", "relative-state")
    assert main(["runtime", "show"]) == 2
    assert "MCP_STATE_DIR must be an absolute path" in capsys.readouterr().err



def test_uninstall_purge_refuses_to_delete_managed_package_state(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("MCP_STATE_DIR", raising=False)
    package_manifest = (
        tmp_path
        / "state"
        / "local-mcp-server"
        / "mcp"
        / "sandboxes"
        / "example"
        / "packages"
        / "npm"
        / "package.json"
    )
    package_manifest.parent.mkdir(parents=True)
    package_manifest.write_text('{"private": true, "dependencies": {}}\n', encoding="utf-8")

    assert main(["uninstall", "--yes", "--purge"]) != 0
    captured = capsys.readouterr()
    assert "package manifests or lockfiles may be inside" in captured.err
    assert "NO APPLICATION DATA REMOVED" in captured.err
    assert package_manifest.is_file()
