from __future__ import annotations

import json

import pytest

from local_mcp_server.workspace import sandbox_files


def test_list_uses_selected_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str) -> str:
        calls.append((name, command))
        return json.dumps({
            "stdout": json.dumps(["README.md", "src/main.py"]),
            "stderr": "",
            "return_code": 0,
        })

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    assert sandbox_files.list_sandbox_workspace_files("focused") == ["README.md", "src/main.py"]
    assert calls[0][0] == "focused"
    assert "/workspace/project" in calls[0][1]


def test_read_uses_selected_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str) -> str:
        calls.append((name, command))
        return json.dumps({"stdout": "hello\n", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    assert sandbox_files.read_sandbox_workspace_text_file("focused", "README.md") == "hello\n"
    assert calls[0][0] == "focused"
    assert "/workspace/project" in calls[0][1]
    assert "README.md" in calls[0][1]


def test_read_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="Path must not be empty"):
        sandbox_files.read_sandbox_workspace_text_file("focused", "")


def test_read_rejects_nul_path() -> None:
    with pytest.raises(ValueError, match="NUL"):
        sandbox_files.read_sandbox_workspace_text_file("focused", "README.md\x00")


def test_read_rejects_overlong_path() -> None:
    with pytest.raises(ValueError, match="too long"):
        sandbox_files.read_sandbox_workspace_text_file("focused", "a" * 4097)


def test_sandbox_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_execute_sandbox(*, name: str, command: str) -> str:
        return json.dumps({
            "stdout": "",
            "stderr": "Requested path is outside the workspace.",
            "return_code": 1,
        })

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    with pytest.raises(ValueError, match="outside the workspace"):
        sandbox_files.read_sandbox_workspace_text_file("focused", "../etc/passwd")

