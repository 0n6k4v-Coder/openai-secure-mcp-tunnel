from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from local_mcp_server.cli import workspace_broker as broker


def test_is_protected_path(
    tmp_path: Path,
) -> None:
    assert broker._is_protected_path(
        tmp_path / ".secrets",
        tmp_path,
    )

    assert broker._is_protected_path(
        tmp_path / ".secrets" / "token",
        tmp_path,
    )

    assert broker._is_protected_path(
        tmp_path / ".state" / "nested" / "file.json",
        tmp_path,
    )

    assert broker._is_protected_path(
        tmp_path / "deploy" / "openshell" / "jwt" / "signing.pem",
        tmp_path,
    )

    assert not broker._is_protected_path(
        tmp_path / "src" / "main.py",
        tmp_path,
    )


def test_validate_protected_path_permissions_accepts_owner_only(
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / ".env"
    secret_file.write_text(
        "TEST=value\n",
        encoding="utf-8",
    )
    os.chmod(
        secret_file,
        0o600,
    )

    secrets_directory = tmp_path / ".secrets"
    secrets_directory.mkdir()
    os.chmod(
        secrets_directory,
        0o700,
    )

    state_directory = tmp_path / ".state"
    state_directory.mkdir()
    os.chmod(
        state_directory,
        0o700,
    )

    jwt_directory = tmp_path / "deploy" / "openshell" / "jwt"
    jwt_directory.mkdir(
        parents=True,
    )
    os.chmod(
        jwt_directory,
        0o700,
    )

    broker._validate_protected_path_permissions(tmp_path)


def test_validate_protected_path_permissions_rejects_world_readable_secret(
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / ".env"
    secret_file.write_text(
        "TEST=value\n",
        encoding="utf-8",
    )
    os.chmod(
        secret_file,
        0o644,
    )

    with pytest.raises(
        RuntimeError,
        match="unsafe permissions",
    ):
        broker._validate_protected_path_permissions(tmp_path)


def test_validate_protected_path_permissions_rejects_group_accessible_directory(
    tmp_path: Path,
) -> None:
    secrets_directory = tmp_path / ".secrets"
    secrets_directory.mkdir()
    os.chmod(
        secrets_directory,
        0o750,
    )

    with pytest.raises(
        RuntimeError,
        match="unsafe permissions",
    ):
        broker._validate_protected_path_permissions(tmp_path)


def test_provision_sandbox_acl_requires_setfacl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        broker.shutil,
        "which",
        lambda name: None,
    )

    with pytest.raises(
        RuntimeError,
        match="setfacl is required",
    ):
        broker._provision_sandbox_acl(tmp_path)


def test_provision_sandbox_acl_applies_existing_and_default_acls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_directory = tmp_path / "src"
    source_directory.mkdir()

    source_file = source_directory / "main.py"
    source_file.write_text(
        "print('ok')\n",
        encoding="utf-8",
    )

    protected_directory = tmp_path / ".secrets"
    protected_directory.mkdir()
    os.chmod(
        protected_directory,
        0o700,
    )

    commands: list[list[str]] = []

    monkeypatch.setattr(
        broker.shutil,
        "which",
        lambda name: "/usr/bin/setfacl",
    )

    def fake_run(
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        broker,
        "_run_command",
        fake_run,
    )

    broker._provision_sandbox_acl(tmp_path)

    assert [
        "/usr/bin/setfacl",
        "-m",
        "u:10001:rwx",
        str(tmp_path),
    ] in commands

    assert [
        "/usr/bin/setfacl",
        "-m",
        "u:10001:rwx",
        str(source_directory),
    ] in commands

    assert [
        "/usr/bin/setfacl",
        "-m",
        "u:10001:rwX",
        str(source_file),
    ] in commands

    assert [
        "/usr/bin/setfacl",
        "-m",
        "d:u:10001:rwx",
        str(tmp_path),
    ] in commands

    assert [
        "/usr/bin/setfacl",
        "-m",
        "d:u:10001:rwx",
        str(source_directory),
    ] in commands

    assert not any(str(protected_directory) in command for command in commands)


def test_provision_sandbox_acl_does_not_follow_symlink_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_directory = tmp_path / "real"
    real_directory.mkdir()

    linked_directory = tmp_path / "linked"
    linked_directory.symlink_to(
        real_directory,
        target_is_directory=True,
    )

    commands: list[list[str]] = []

    monkeypatch.setattr(
        broker.shutil,
        "which",
        lambda name: "/usr/bin/setfacl",
    )

    def fake_run(
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        broker,
        "_run_command",
        fake_run,
    )

    broker._provision_sandbox_acl(tmp_path)

    assert not any(str(linked_directory) in command for command in commands)
