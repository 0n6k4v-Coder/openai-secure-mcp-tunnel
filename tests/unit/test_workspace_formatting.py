from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from local_mcp_server.infrastructure.openshell import sandbox_files
from local_mcp_server.workspace import formatting


def test_write_script_formats_javascript_when_prettier_is_available(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    prettier = fake_bin / "prettier"
    prettier.write_text(
        "#!/bin/sh\ncat >/dev/null\nprintf 'const value = 1;'\n",
        encoding="utf-8",
    )
    prettier.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    script = sandbox_files._WRITE_TO_FILE_SCRIPT.replace(
        '"/workspace/project"', repr(str(workspace))
    )

    result = subprocess.run(
        [sys.executable, "-c", script, "src/app.js", "true"],
        input="const value=1",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (workspace / "src/app.js").read_text(encoding="utf-8") == "const value = 1;"
    payload = json.loads(result.stdout)
    assert payload["path"] == "src/app.js"
    assert payload["formatting"] == "formatted with Prettier"


def test_write_succeeds_with_warning_when_formatter_is_missing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_bin)
    script = sandbox_files._WRITE_TO_FILE_SCRIPT.replace(
        '"/workspace/project"', repr(str(workspace))
    )

    result = subprocess.run(
        [sys.executable, "-c", script, "src/app.js", "true"],
        input="const value=1",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (workspace / "src/app.js").read_text(encoding="utf-8") == "const value=1"
    assert json.loads(result.stdout)["formatting"] == (
        "skipped: Prettier is not installed in the target sandbox"
    )


def test_replace_script_formats_updated_javascript_when_prettier_is_available(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "src/app.js"
    target.parent.mkdir()
    target.write_text("const value=1", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    prettier = fake_bin / "prettier"
    prettier.write_text(
        "#!/bin/sh\ncat >/dev/null\nprintf 'const value = 2;'\n",
        encoding="utf-8",
    )
    prettier.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    script = sandbox_files._REPLACE_FILE_CONTENT_SCRIPT.replace(
        '"/workspace/project"', repr(str(workspace))
    )

    result = subprocess.run(
        [sys.executable, "-c", script, "src/app.js", "false"],
        input=json.dumps(
            {"target_content": "value=1", "replacement_content": "value=2"}
        ),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8") == "const value = 2;"
    payload = json.loads(result.stdout)
    assert payload["formatting"] == "formatted with Prettier"


def test_format_text_uses_selected_sandbox_and_reports_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[str], str | bytes | None]] = []

    def fake_execute_sandbox_argv(
        name: str,
        argv: list[str],
        *,
        stdin: bytes | str | None = None,
        timeout_seconds: int = 120,
    ) -> dict[str, object]:
        calls.append((name, argv, stdin))
        return {
            "stdout": json.dumps(
                {"content": "const value = 1;\n", "status": "formatted with Prettier"}
            ),
            "stderr": "",
            "return_code": 0,
        }

    monkeypatch.setattr(formatting, "execute_sandbox_argv", fake_execute_sandbox_argv)
    content, status = formatting.format_text_in_sandbox(
        "selected", "src/app.js", "const value=1"
    )

    assert content == "const value = 1;\n"
    assert status == "formatted with Prettier"
    assert calls[0][0] == "selected"
    assert calls[0][1][0:3] == ["python", "-c", formatting._FORMAT_RUNNER]
    assert calls[0][1][-1] == "src/app.js"
    assert calls[0][2] == "const value=1"


def test_format_text_rejects_paths_outside_workspace() -> None:
    with pytest.raises(ValueError, match="relative workspace path"):
        formatting.format_text_in_sandbox("selected", "../outside.js", "x")


def test_formatting_result_includes_warning_without_changing_legacy_paths() -> None:
    assert sandbox_files._formatting_result("src/app.py") == "src/app.py"
    assert sandbox_files._formatting_result(
        json.dumps(
            {
                "path": "src/app.py",
                "formatting": "skipped: Ruff is not installed in the target sandbox",
            }
        )
    ) == (
        "src/app.py\nFormatting: skipped: Ruff is not installed in the target sandbox"
    )
