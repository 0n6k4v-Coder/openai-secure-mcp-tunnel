from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from local_mcp_server.infrastructure.openshell import sandbox_files


def test_list_uses_selected_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command))
        return json.dumps(
            {
                "stdout": json.dumps(["README.md", "src/main.py"]),
                "stderr": "",
                "return_code": 0,
            }
        )

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    assert sandbox_files.list_sandbox_workspace_files("focused") == [
        "README.md",
        "src/main.py",
    ]
    assert calls[0][0] == "focused"
    assert "/workspace/project" in calls[0][1]


def test_read_uses_selected_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command))
        return json.dumps({"stdout": "hello\n", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    assert (
        sandbox_files.read_sandbox_workspace_text_file("focused", "README.md")
        == "hello\n"
    )
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


def test_write_to_file_uses_selected_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command, kwargs.get("stdin")))
        return json.dumps({"stdout": "src/app.py", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    result = sandbox_files.write_sandbox_file(
        "focused", "src/app.py", "print(1)", overwrite=True
    )
    assert result == "src/app.py"
    assert calls[0][0] == "focused"
    assert "src/app.py" in calls[0][1]
    assert "true" in calls[0][1]
    assert calls[0][2] == b"print(1)"


def test_write_to_file_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="Path must not be empty"):
        sandbox_files.write_sandbox_file("focused", "", "content")

    with pytest.raises(ValueError, match="Content must be a string"):
        sandbox_files.write_sandbox_file("focused", "a.txt", 123)  # type: ignore

    with pytest.raises(ValueError, match="Content is too large"):
        sandbox_files.write_sandbox_file("focused", "a.txt", "x" * 1_000_001)


def test_replace_file_content_uses_selected_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command, kwargs.get("stdin")))
        return json.dumps({"stdout": "README.md", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    result = sandbox_files.replace_sandbox_file_content(
        "focused", "README.md", "old text", "new text", allow_multiple=False
    )
    assert result == "README.md"
    assert calls[0][0] == "focused"
    assert b"old text" in calls[0][2]
    assert b"new text" in calls[0][2]



def test_create_directory_uses_selected_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command))
        return json.dumps({"stdout": "newdir", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    result = sandbox_files.create_sandbox_workspace_directory("focused", "newdir")
    assert result == "newdir"
    assert calls[0][0] == "focused"
    assert "newdir" in calls[0][1]


def test_rename_path_uses_selected_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command))
        return json.dumps({"stdout": "dest.txt", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    result = sandbox_files.rename_sandbox_workspace_path(
        "focused", "src.txt", "dest.txt"
    )
    assert result == "dest.txt"
    assert calls[0][0] == "focused"
    assert "src.txt" in calls[0][1]
    assert "dest.txt" in calls[0][1]


def test_delete_file_uses_selected_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command))
        return json.dumps({"stdout": "old.txt", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    result = sandbox_files.delete_sandbox_workspace_file("focused", "old.txt")
    assert result == "old.txt"
    assert calls[0][0] == "focused"
    assert "old.txt" in calls[0][1]


def test_delete_directory_uses_selected_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        calls.append((name, command))
        return json.dumps({"stdout": "olddir", "stderr": "", "return_code": 0})

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    result = sandbox_files.delete_sandbox_workspace_directory("focused", "olddir")
    assert result == "olddir"
    assert calls[0][0] == "focused"
    assert "olddir" in calls[0][1]


def test_sandbox_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_execute_sandbox(*, name: str, command: str, **kwargs) -> str:
        return json.dumps(
            {
                "stdout": "",
                "stderr": "Requested path is outside the workspace.",
                "return_code": 1,
            }
        )

    monkeypatch.setattr(sandbox_files, "execute_sandbox", fake_execute_sandbox)
    with pytest.raises(ValueError, match="outside the workspace"):
        sandbox_files.read_sandbox_workspace_text_file("focused", "../etc/passwd")


def _run_script_in_test_workspace(
    script: str,
    workspace_root: Path,
    args: list[str],
    stdin: bytes = b"",
) -> subprocess.CompletedProcess[str]:
    adapted_script = script.replace('"/workspace/project"', repr(str(workspace_root)))
    return subprocess.run(
        [sys.executable, "-c", adapted_script, *args],
        input=stdin.decode("utf-8"),
        capture_output=True,
        text=True,
    )


def test_script_write_to_file_lifecycle_and_security(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()

    # Create new file with overwrite=True
    res = _run_script_in_test_workspace(
        sandbox_files._WRITE_TO_FILE_SCRIPT,
        ws,
        ["hello.txt", "true"],
        stdin=b"world",
    )
    assert res.returncode == 0
    assert (ws / "hello.txt").read_text() == "world"

    # Overwrite existing file when overwrite=true
    res_dup = _run_script_in_test_workspace(
        sandbox_files._WRITE_TO_FILE_SCRIPT,
        ws,
        ["hello.txt", "true"],
        stdin=b"new",
    )
    assert res_dup.returncode == 0
    assert (ws / "hello.txt").read_text() == "new"

    # Reject overwrite when overwrite=false
    res_no_ow = _run_script_in_test_workspace(
        sandbox_files._WRITE_TO_FILE_SCRIPT,
        ws,
        ["hello.txt", "false"],
        stdin=b"another",
    )
    assert res_no_ow.returncode != 0
    assert "overwrite is set to False" in res_no_ow.stderr

    # Reject outside workspace
    res_out = _run_script_in_test_workspace(
        sandbox_files._WRITE_TO_FILE_SCRIPT,
        ws,
        ["../outside.txt", "true"],
        stdin=b"evil",
    )
    assert res_out.returncode != 0
    assert "outside the workspace" in res_out.stderr



def test_script_delete_directory_security(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    sub = ws / "subdir"
    sub.mkdir()
    (sub / "file.txt").write_text("ok")

    # Reject deleting workspace root
    res_root = _run_script_in_test_workspace(
        sandbox_files._DELETE_DIRECTORY_SCRIPT,
        ws,
        ["."],
    )
    assert res_root.returncode != 0
    assert "Deleting the workspace root is not allowed" in res_root.stderr

    # Reject deleting regular file
    res_file = _run_script_in_test_workspace(
        sandbox_files._DELETE_DIRECTORY_SCRIPT,
        ws,
        ["subdir/file.txt"],
    )
    assert res_file.returncode != 0
    assert "not a directory" in res_file.stderr

    # Successfully delete directory
    res_del = _run_script_in_test_workspace(
        sandbox_files._DELETE_DIRECTORY_SCRIPT,
        ws,
        ["subdir"],
    )
    assert res_del.returncode == 0
    assert not sub.exists()


def test_script_symlink_rejection(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()

    real_file = ws / "real.txt"
    real_file.write_text("orig")
    link_file = ws / "link.txt"
    link_file.symlink_to(real_file)

    # Reject write to file on existing symlink
    res = _run_script_in_test_workspace(
        sandbox_files._WRITE_TO_FILE_SCRIPT,
        ws,
        ["link.txt", "true"],
        stdin=b"bad",
    )
    assert res.returncode != 0
    assert "symbolic link" in res.stderr

    # Reject delete directory on symlink
    real_dir = ws / "realdir"
    real_dir.mkdir()
    link_dir = ws / "linkdir"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    res_dir = _run_script_in_test_workspace(
        sandbox_files._DELETE_DIRECTORY_SCRIPT,
        ws,
        ["linkdir"],
    )
    assert res_dir.returncode != 0
    assert "symbolic link" in res_dir.stderr


def test_script_replace_file_content(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    file_path = ws / "code.py"
    file_path.write_text("def hello():\n    return 1\n")

    # Replace single occurrence
    payload = json.dumps({"target_content": "return 1", "replacement_content": "return 42"})
    res = _run_script_in_test_workspace(
        sandbox_files._REPLACE_FILE_CONTENT_SCRIPT,
        ws,
        ["code.py", "false"],
        stdin=payload.encode("utf-8"),
    )
    assert res.returncode == 0
    assert file_path.read_text() == "def hello():\n    return 42\n"

    # Reject when target not found
    payload_missing = json.dumps({"target_content": "missing_func()", "replacement_content": "noop"})
    res_missing = _run_script_in_test_workspace(
        sandbox_files._REPLACE_FILE_CONTENT_SCRIPT,
        ws,
        ["code.py", "false"],
        stdin=payload_missing.encode("utf-8"),
    )
    assert res_missing.returncode != 0
    assert "not found" in res_missing.stderr


def test_script_rename_path(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    src = ws / "source.txt"
    src.write_text("data")

    res = _run_script_in_test_workspace(
        sandbox_files._RENAME_PATH_SCRIPT,
        ws,
        ["source.txt", "target.txt"],
    )
    assert res.returncode == 0
    assert not src.exists()
    assert (ws / "target.txt").read_text() == "data"

