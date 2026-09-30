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


def test_canonicalize_host_workspace_rejects_sensitive_paths() -> None:
    sensitive = (
        Path("/"),
        Path("/etc"),
        Path("/proc"),
        Path("/sys"),
        Path("/dev"),
        Path("/run"),
        Path("/var/run"),
        Path("/var/lib/docker"),
    )

    for path in sensitive:
        if not path.exists():
            continue

        with pytest.raises(
            ValueError,
            match="not allowed|filesystem root",
        ):
            workspace.canonicalize_host_workspace(
                str(path),
            )


def test_canonicalize_host_workspace_requires_absolute_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="absolute",
    ):
        workspace.canonicalize_host_workspace(
            "relative/path",
        )

    missing = tmp_path / "missing"

    with pytest.raises(
        ValueError,
        match="does not exist",
    ):
        workspace.canonicalize_host_workspace(
            str(missing),
        )


@pytest.mark.skipif(
    not hasattr(os, "symlink"),
    reason="Symbolic links are not supported.",
)
def test_canonicalize_host_workspace_resolves_symlink(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real-workspace"
    real.mkdir()

    link = tmp_path / "workspace-link"
    link.symlink_to(
        real,
        target_is_directory=True,
    )

    assert (
        workspace.canonicalize_host_workspace(
            str(link),
        )
        == real.resolve()
    )


def test_create_workspace_grant_rejects_read_only_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workspace,
        "GRANTS_READ_ONLY",
        True,
    )

    with pytest.raises(
        RuntimeError,
        match="read-only",
    ):
        workspace.create_workspace_grant(
            str(tmp_path),
        )


def test_create_workspace_grant_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "grants.json"

    monkeypatch.setattr(
        workspace,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )
    monkeypatch.setattr(
        workspace,
        "GRANTS_READ_ONLY",
        False,
    )

    grant = workspace.create_workspace_grant(
        str(tmp_path),
    )

    assert grant["target"] == "/workspace/project"
    assert grant["read_only"] == "false"
    assert grant["host_path"] == str(tmp_path.resolve())

    resolved = workspace.resolve_workspace_grant(
        grant["workspace_id"],
    )

    assert resolved == tmp_path.resolve()


def test_list_workspace_grants_does_not_require_host_path_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "grants.json"

    grants_file.write_text(
        (
            '{\n'
            '  "ws_test123": "/host/path/not-visible-in-container"\n'
            '}\n'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        workspace,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    grants = workspace.list_workspace_grants()

    assert grants == [
        {
            "workspace_id": "ws_test123",
            "host_path": "/host/path/not-visible-in-container",
            "target": "/workspace/project",
            "read_only": "false",
        }
    ]

    def test_resolve_workspace_grant_does_not_require_host_path_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "grants.json"

    grants_file.write_text(
        (
            '{\n'
            '  "ws_test123": "/host/path/not-visible-in-container"\n'
            '}\n'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        workspace,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    resolved = workspace.resolve_workspace_grant(
        "ws_test123",
    )

    assert resolved == Path(
        "/host/path/not-visible-in-container"
    )