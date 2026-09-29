from __future__ import annotations

import os
import shutil
from pathlib import Path


WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_DIR", "/app/workspace")).resolve()

MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 1_000_000


def resolve_workspace_path(relative_path: str) -> Path:
    """Resolve a user-supplied path while enforcing the workspace boundary."""
    if not relative_path:
        raise ValueError("Path must not be empty.")

    candidate = WORKSPACE_ROOT / relative_path
    resolved = candidate.resolve()

    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError("Requested path is outside the workspace.") from exc

    return resolved


def list_workspace_files() -> list[str]:
    """Return regular files below the workspace."""
    if not WORKSPACE_ROOT.exists():
        return []

    results: list[str] = []

    for path in WORKSPACE_ROOT.rglob("*"):
        try:
            resolved = path.resolve()

            if not resolved.is_file():
                continue

            resolved.relative_to(WORKSPACE_ROOT)

            results.append(resolved.relative_to(WORKSPACE_ROOT).as_posix())

        except (OSError, ValueError):
            continue

    return sorted(results)


def read_workspace_text_file(relative_path: str) -> str:
    """Read a UTF-8 text file from the workspace."""
    target = resolve_workspace_path(relative_path)

    if not target.is_file():
        raise ValueError("Requested path is not a regular file.")

    size = target.stat().st_size

    if size > MAX_READ_BYTES:
        raise ValueError("Requested file is too large.")

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Requested file is not valid UTF-8 text.") from exc


def create_workspace_file(
    relative_path: str,
    content: str,
) -> str:
    """Create a new UTF-8 text file in the workspace."""
    target = resolve_workspace_path(relative_path)

    if target.exists():
        raise ValueError("A file or directory already exists at that path.")

    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        raise ValueError("Content is too large.")

    target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(
        content,
        encoding="utf-8",
    )

    return target.relative_to(WORKSPACE_ROOT).as_posix()


def write_workspace_file(
    relative_path: str,
    content: str,
) -> str:
    """Replace the contents of an existing UTF-8 text file."""
    target = resolve_workspace_path(relative_path)

    if not target.is_file():
        raise ValueError("Requested path is not a regular file.")

    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        raise ValueError("Content is too large.")

    target.write_text(
        content,
        encoding="utf-8",
    )

    return target.relative_to(WORKSPACE_ROOT).as_posix()


def create_workspace_directory(relative_path: str) -> str:
    """Create a directory inside the workspace."""
    target = resolve_workspace_path(relative_path)

    if target.exists():
        raise ValueError("A file or directory already exists at that path.")

    target.mkdir(
        parents=True,
        exist_ok=False,
    )

    return target.relative_to(WORKSPACE_ROOT).as_posix()


def rename_workspace_path(
    relative_path: str,
    new_relative_path: str,
) -> str:
    """Rename a file or directory within the workspace."""
    source = resolve_workspace_path(relative_path)
    destination = resolve_workspace_path(new_relative_path)

    if not source.exists():
        raise ValueError("Source path does not exist.")

    if destination.exists():
        raise ValueError("Destination path already exists.")

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source.rename(destination)

    return destination.relative_to(WORKSPACE_ROOT).as_posix()


def delete_workspace_file(relative_path: str) -> str:
    """Delete a regular file inside the workspace."""
    target = resolve_workspace_path(relative_path)

    if not target.is_file():
        raise ValueError("Requested path is not a regular file.")

    target.unlink()

    return target.relative_to(WORKSPACE_ROOT).as_posix()


def delete_workspace_directory(relative_path: str) -> str:
    """Delete a directory tree inside the workspace."""
    if not relative_path:
        raise ValueError("Path must not be empty.")

    requested = WORKSPACE_ROOT / relative_path

    if requested == WORKSPACE_ROOT:
        raise ValueError("Deleting the workspace root is not allowed.")

    if requested.is_symlink():
        raise ValueError("Requested path must not be a symbolic link.")

    target = requested.resolve()

    try:
        target.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError("Requested path is outside the workspace.") from exc

    if target == WORKSPACE_ROOT:
        raise ValueError("Deleting the workspace root is not allowed.")

    if not target.exists():
        raise ValueError("Requested directory does not exist.")

    if not target.is_dir():
        raise ValueError("Requested path is not a directory.")

    shutil.rmtree(target)

    return target.relative_to(WORKSPACE_ROOT).as_posix()
