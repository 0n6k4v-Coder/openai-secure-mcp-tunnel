from __future__ import annotations

import json
import os
import shlex

SANDBOX_WORKSPACE_ROOT = "/workspace/project"
MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 1_000_000
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

_CREATE_FILE_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
if os.path.islink(requested):
    raise SystemExit("Requested path must not be a symbolic link.")

resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if os.path.exists(resolved):
    raise SystemExit("A file or directory already exists at that path.")

content = sys.stdin.buffer.read()
if len(content) > 1_000_000:
    raise SystemExit("Content is too large.")

parent = os.path.dirname(resolved)
os.makedirs(parent, exist_ok=True)

with open(resolved, "wb") as handle:
    handle.write(content)

sys.stdout.write(os.path.relpath(resolved, root))
""".strip()

_WRITE_FILE_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
if os.path.islink(requested):
    raise SystemExit("Requested path must not be a symbolic link.")

resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if not os.path.isfile(resolved):
    raise SystemExit("Requested path is not a regular file.")

content = sys.stdin.buffer.read()
if len(content) > 1_000_000:
    raise SystemExit("Content is too large.")

with open(resolved, "wb") as handle:
    handle.write(content)

sys.stdout.write(os.path.relpath(resolved, root))
""".strip()

_CREATE_DIRECTORY_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if os.path.exists(resolved):
    raise SystemExit("A file or directory already exists at that path.")

os.makedirs(resolved, exist_ok=False)
sys.stdout.write(os.path.relpath(resolved, root))
""".strip()

_RENAME_PATH_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]
new_relative_path = sys.argv[2]

if not relative_path or not new_relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path) or os.path.isabs(new_relative_path):
    raise SystemExit("Requested path must be relative.")

source = os.path.realpath(os.path.join(root, relative_path))
destination = os.path.realpath(os.path.join(root, new_relative_path))

for target in (source, destination):
    try:
        common = os.path.commonpath([root, target])
    except ValueError as exc:
        raise SystemExit("Requested path is outside the workspace.") from exc
    if common != root:
        raise SystemExit("Requested path is outside the workspace.")

if not os.path.exists(source):
    raise SystemExit("Source path does not exist.")

if os.path.exists(destination):
    raise SystemExit("Destination path already exists.")

dest_parent = os.path.dirname(destination)
os.makedirs(dest_parent, exist_ok=True)
os.rename(source, destination)
sys.stdout.write(os.path.relpath(destination, root))
""".strip()

_DELETE_FILE_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if not os.path.isfile(resolved):
    raise SystemExit("Requested path is not a regular file.")

os.unlink(resolved)
sys.stdout.write(os.path.relpath(resolved, root))
""".strip()

_DELETE_DIRECTORY_SCRIPT = r"""
import os
import shutil
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
if requested == root or relative_path == ".":
    raise SystemExit("Deleting the workspace root is not allowed.")
if os.path.islink(requested):
    raise SystemExit("Requested path must not be a symbolic link.")

resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root or resolved == root:
    raise SystemExit("Deleting the workspace root is not allowed." if resolved == root else "Requested path is outside the workspace.")

if not os.path.exists(resolved):
    raise SystemExit("Requested directory does not exist.")

if not os.path.isdir(resolved):
    raise SystemExit("Requested path is not a directory.")

shutil.rmtree(resolved)
sys.stdout.write(os.path.relpath(resolved, root))
""".strip()


def _validate_relative_path(relative_path: str) -> None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Path must not be empty.")
    if "\x00" in relative_path:
        raise ValueError("Path must not contain NUL bytes.")
    if len(relative_path.encode("utf-8")) > MAX_RELATIVE_PATH_BYTES:
        raise ValueError("Path is too long.")
    if relative_path.startswith("/") or os.path.isabs(relative_path):
        raise ValueError("Requested path must be relative.")


def _validate_content(content: str) -> bytes:
    if not isinstance(content, str):
        raise ValueError("Content must be a string.")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        raise ValueError("Content is too large.")
    return encoded


def execute_sandbox(*args, **kwargs):
    from .sandbox import execute_sandbox as _execute_sandbox

    return _execute_sandbox(*args, **kwargs)


def validate_name(*args, **kwargs):
    from .policy import validate_name as _validate_name

    return _validate_name(*args, **kwargs)


def _execute_workspace_command(
    sandbox_name: str,
    command: str,
    *,
    stdin: bytes | str | None = None,
) -> str:
    validate_name(sandbox_name)
    kwargs = {}
    if stdin is not None:
        kwargs["stdin"] = stdin
    result = json.loads(
        execute_sandbox(
            name=sandbox_name,
            command=command,
            **kwargs,
        )
    )
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
    if not isinstance(result, list) or not all(
        isinstance(value, str) for value in result
    ):
        raise RuntimeError("Sandbox workspace listing returned an invalid result.")
    return list(result)


def read_sandbox_workspace_text_file(sandbox_name: str, relative_path: str) -> str:
    _validate_relative_path(relative_path)
    command = (
        "python -c " + shlex.quote(_READ_FILE_SCRIPT) + " " + shlex.quote(relative_path)
    )
    return _execute_workspace_command(sandbox_name, command)


def create_sandbox_workspace_file(
    sandbox_name: str,
    relative_path: str,
    content: str,
) -> str:
    _validate_relative_path(relative_path)
    encoded = _validate_content(content)
    command = (
        "python -c "
        + shlex.quote(_CREATE_FILE_SCRIPT)
        + " "
        + shlex.quote(relative_path)
    )
    return _execute_workspace_command(sandbox_name, command, stdin=encoded)


def write_sandbox_workspace_file(
    sandbox_name: str,
    relative_path: str,
    content: str,
) -> str:
    _validate_relative_path(relative_path)
    encoded = _validate_content(content)
    command = (
        "python -c "
        + shlex.quote(_WRITE_FILE_SCRIPT)
        + " "
        + shlex.quote(relative_path)
    )
    return _execute_workspace_command(sandbox_name, command, stdin=encoded)


def create_sandbox_workspace_directory(
    sandbox_name: str,
    relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    command = (
        "python -c "
        + shlex.quote(_CREATE_DIRECTORY_SCRIPT)
        + " "
        + shlex.quote(relative_path)
    )
    return _execute_workspace_command(sandbox_name, command)


def rename_sandbox_workspace_path(
    sandbox_name: str,
    relative_path: str,
    new_relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    _validate_relative_path(new_relative_path)
    command = (
        "python -c "
        + shlex.quote(_RENAME_PATH_SCRIPT)
        + " "
        + shlex.quote(relative_path)
        + " "
        + shlex.quote(new_relative_path)
    )
    return _execute_workspace_command(sandbox_name, command)


def delete_sandbox_workspace_file(
    sandbox_name: str,
    relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    command = (
        "python -c "
        + shlex.quote(_DELETE_FILE_SCRIPT)
        + " "
        + shlex.quote(relative_path)
    )
    return _execute_workspace_command(sandbox_name, command)


def delete_sandbox_workspace_directory(
    sandbox_name: str,
    relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    command = (
        "python -c "
        + shlex.quote(_DELETE_DIRECTORY_SCRIPT)
        + " "
        + shlex.quote(relative_path)
    )
    return _execute_workspace_command(sandbox_name, command)
