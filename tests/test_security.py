from __future__ import annotations

import os
from pathlib import Path

import pytest

from local_mcp_server import workspace


@pytest.fixture
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        workspace,
        "WORKSPACE_ROOT",
        tmp_path.resolve(),
    )

    return tmp_path


def test_delete_workspace_directory(
    workspace_root: Path,
) -> None:
    target = workspace_root / "repository"

    (target / "src").mkdir(parents=True)
    (target / "README.md").write_text(
        "test",
        encoding="utf-8",
    )
    (target / "src" / "main.py").write_text(
        "print('test')",
        encoding="utf-8",
    )

    result = workspace.delete_workspace_directory(
        "repository",
    )

    assert result == "repository"
    assert not target.exists()


def test_delete_workspace_directory_rejects_workspace_root(
    workspace_root: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="workspace root",
    ):
        workspace.delete_workspace_directory(".")


def test_delete_workspace_directory_rejects_path_outside_workspace(
    workspace_root: Path,
) -> None:
    outside = workspace_root.parent / "outside"
    outside.mkdir()

    with pytest.raises(
        ValueError,
        match="outside the workspace",
    ):
        workspace.delete_workspace_directory("../outside")


def test_delete_workspace_directory_rejects_missing_directory(
    workspace_root: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="does not exist",
    ):
        workspace.delete_workspace_directory(
            "missing",
        )


def test_delete_workspace_directory_rejects_regular_file(
    workspace_root: Path,
) -> None:
    target = workspace_root / "file.txt"

    target.write_text(
        "test",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="not a directory",
    ):
        workspace.delete_workspace_directory(
            "file.txt",
        )


@pytest.mark.skipif(
    not hasattr(os, "symlink"),
    reason="Symbolic links are not supported.",
)
def test_delete_workspace_directory_rejects_symlink(
    workspace_root: Path,
) -> None:
    target = workspace_root / "real-directory"
    target.mkdir()

    link = workspace_root / "directory-link"
    link.symlink_to(
        target,
        target_is_directory=True,
    )

    with pytest.raises(
        ValueError,
        match="symbolic link",
    ):
        workspace.delete_workspace_directory(
            "directory-link",
        )

    assert target.exists()


@pytest.mark.skipif(
    not hasattr(os, "symlink"),
    reason="Symbolic links are not supported.",
)
def test_create_workspace_file_rejects_symlink(
    workspace_root: Path,
) -> None:
    target = workspace_root / "real-file.txt"
    target.write_text(
        "original",
        encoding="utf-8",
    )

    link = workspace_root / "file-link.txt"
    link.symlink_to(target)

    with pytest.raises(
        ValueError,
        match="symbolic link",
    ):
        workspace.create_workspace_file(
            "file-link.txt",
            "replacement",
        )

    assert target.read_text(encoding="utf-8") == "original"
    assert link.is_symlink()
