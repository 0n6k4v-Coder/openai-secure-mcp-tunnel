from __future__ import annotations

import json
import shlex

from ..sandbox import execute_sandbox, validate_name

SANDBOX_WORKSPACE_ROOT = "/workspace/project"
MAX_READ_BYTES = 1_000_000
MAX_RELATIVE_PATH_BYTES = 4_096

_LIST_FILES_COMMAND = r"""python -c '
import json
import os
root = "/workspace/project"
results = []
for base, directories, files in os.walk(root, followlinks=False):
    for name in files:
        path = os.path.join(base, name)
        resolved = os.path.realpath(path)
        try:
            common = os.path.commonpath([root, resolved])
        except ValueError:
            continue
        if common == root and os.path.isfile(resolved):
            results.append(os.path.relpath(resolved, root))
print(json.dumps(sorted(set(results)), ensure_ascii=False))
'"""

_READ_FILE_SCRIPT = r"""
import os
import sys
root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]
if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")
resolved = os.path.realpath(os.path.join(root, relative_path))
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc
if common != root:
    raise SystemExit("Requested path is outside the workspace.")
if not os.path.isfile(resolved):
    raise SystemExit("Requested path is not a regular file.")
if os.path.getsize(resolved) > 1_000_000:
    raise SystemExit("Requested file is too large.")
try:
    with open(resolved, "r", encoding="utf-8") as handle:
        content = handle.read()
except UnicodeDecodeError as exc:
    raise SystemExit("Requested file is not valid UTF-8 text.") from exc
sys.stdout.write(content)
""".strip()


def _execute_workspace_command(sandbox_name: str, command: str) -> str:
    validate_name(sandbox_name)
    result = json.loads(execute_sandbox(name=sandbox_name, command=command))
    if result.get("return_code") != 0:
        stderr = result.get("stderr", "")
        message = stderr.strip() if isinstance(stderr, str) else ""
        raise ValueError(message or "Sandbox workspace command failed.")
    stdout = result.get("stdout", "")
    if not isinstance(stdout, str):
        raise RuntimeError("Sandbox workspace command returned invalid stdout.")
    return stdout


def list_sandbox_workspace_files(sandbox_name: str) -> list[str]:
    output = _execute_workspace_command(sandbox_name, _LIST_FILES_COMMAND)
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Sandbox workspace listing returned invalid JSON.") from exc
    if not isinstance(result, list) or not all(isinstance(value, str) for value in result):
        raise RuntimeError("Sandbox workspace listing returned an invalid result.")
    return list(result)


def read_sandbox_workspace_text_file(sandbox_name: str, relative_path: str) -> str:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Path must not be empty.")
    if "\x00" in relative_path:
        raise ValueError("Path must not contain NUL bytes.")
    if len(relative_path.encode("utf-8")) > MAX_RELATIVE_PATH_BYTES:
        raise ValueError("Path is too long.")
    command = "python -c " + shlex.quote(_READ_FILE_SCRIPT) + " -- " + shlex.quote(relative_path)
    return _execute_workspace_command(sandbox_name, command)

