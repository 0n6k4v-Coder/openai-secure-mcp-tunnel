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
