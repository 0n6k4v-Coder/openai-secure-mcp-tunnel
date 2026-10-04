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


def test_is_excluded_path(
    tmp_path: Path,
) -> None:
    assert broker._is_excluded_path(
        tmp_path / ".git",
        tmp_path,
    )

    assert broker._is_excluded_path(
        tmp_path / ".git" / "objects" / "object",
        tmp_path,
    )

    assert broker._is_excluded_path(
        tmp_path / ".venv",
        tmp_path,
    )

    assert broker._is_excluded_path(
        tmp_path / ".venv" / "lib" / "python3.14" / "site-packages",
        tmp_path,
    )

    assert broker._is_excluded_path(
        tmp_path / "deploy" / "docker" / "workspace-acl-helper",
        tmp_path,
    )

    assert broker._is_excluded_path(
        tmp_path / "src" / "__pycache__" / "main.pyc",
        tmp_path,
    )

    assert not broker._is_excluded_path(
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


def test_provision_sandbox_acl_uses_acl_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        broker,
        "_run_acl_helper",
        lambda path, *, operation, host_uid=None, host_gid=None: observed.update(
            {
                "path": path,
                "operation": operation,
                "host_uid": host_uid,
                "host_gid": host_gid,
            }
        ),
    )

    broker._provision_sandbox_acl(
        tmp_path,
        host_uid=2000,
        host_gid=2001,
    )

    assert observed == {
        "path": tmp_path,
        "operation": "provision-sandbox-acl",
        "host_uid": 2000,
        "host_gid": 2001,
    }


def test_acl_helper_uses_current_host_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    monkeypatch.setattr(
        broker.os,
        "getuid",
        lambda: 2001,
    )
    monkeypatch.setattr(
        broker.os,
        "getgid",
        lambda: 2002,
    )
    monkeypatch.setattr(
        broker.shutil,
        "which",
        lambda name: "/usr/bin/docker",
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

    broker._run_acl_helper(
        tmp_path,
        operation="provision-sandbox-acl",
    )

    assert commands == [
        [
            "/usr/bin/docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "DAC_OVERRIDE",
            "--cap-add",
            "FOWNER",
            "--user",
            "0:0",
            "--mount",
            f"type=bind,source={tmp_path.resolve()},target=/workspace",
            broker.ACL_HELPER_IMAGE,
            "provision-sandbox-acl",
            str(broker.SANDBOX_UID),
            "2001",
        ]
    ]


def test_provision_sandbox_acl_rejects_unsafe_protected_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.setattr(
        broker,
        "_run_acl_helper",
        lambda *args, **kwargs: pytest.fail(
            "ACL helper must not run for an unsafe workspace."
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="unsafe permissions",
    ):
        broker._provision_sandbox_acl(tmp_path)


def test_acl_helper_requires_docker(
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
        match="docker is required",
    ):
        broker._run_acl_helper(
            tmp_path,
            operation="provision-sandbox-acl",
            host_uid=2000,
            host_gid=2001,
        )


def test_acl_helper_uses_narrow_docker_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    monkeypatch.setattr(
        broker.shutil,
        "which",
        lambda name: "/usr/bin/docker",
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

    broker._run_acl_helper(
        tmp_path,
        operation="provision-sandbox-acl",
        host_uid=1000,
        host_gid=1000,
    )

    assert commands == [
        [
            "/usr/bin/docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "DAC_OVERRIDE",
            "--cap-add",
            "FOWNER",
            "--user",
            "0:0",
            "--mount",
            f"type=bind,source={tmp_path.resolve()},target=/workspace",
            broker.ACL_HELPER_IMAGE,
            "provision-sandbox-acl",
            str(broker.SANDBOX_UID),
            "1000",
        ]
    ]


def test_remove_sandbox_acl_with_helper_uses_narrow_docker_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    monkeypatch.setattr(
        broker.shutil,
        "which",
        lambda name: "/usr/bin/docker",
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

    broker._remove_sandbox_acl_with_helper(
        tmp_path,
        host_uid=1000,
        host_gid=1000,
    )

    assert commands == [
        [
            "/usr/bin/docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "DAC_OVERRIDE",
            "--cap-add",
            "FOWNER",
            "--user",
            "0:0",
            "--mount",
            f"type=bind,source={tmp_path.resolve()},target=/workspace",
            broker.ACL_HELPER_IMAGE,
            "remove-sandbox-acl",
            str(broker.SANDBOX_UID),
            "1000",
        ]
    ]


def test_create_workspace_grant_records_host_uid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "workspace-grants.json"
    host_path = tmp_path / "workspace"
    host_path.mkdir()

    monkeypatch.setattr(
        broker.workspace_service,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )
    monkeypatch.setattr(
        broker.os,
        "getuid",
        lambda: 2002,
    )
    monkeypatch.setattr(
        broker.os,
        "getgid",
        lambda: 2004,
    )
    monkeypatch.setattr(
        broker,
        "canonicalize_host_workspace",
        lambda value: host_path,
    )
    monkeypatch.setattr(
        broker,
        "_provision_sandbox_acl",
        lambda path, *, host_uid=None, host_gid=None: None,
    )
    monkeypatch.setattr(
        broker,
        "_create_host_backed_volume",
        lambda volume_name, path: None,
    )

    result = broker.create_workspace_grant(str(host_path))

    workspace_id = result["workspace_id"]

    assert result["host_uid"] == 2002
    assert result["host_gid"] == 2004
    assert broker._load_grants()[workspace_id]["host_uid"] == 2002
    assert broker._load_grants()[workspace_id]["host_gid"] == 2004


def test_create_workspace_grant_rolls_back_acl_on_volume_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_path = tmp_path / "workspace"
    host_path.mkdir()

    observed: list[tuple[str, Path]] = []

    monkeypatch.setattr(
        broker,
        "canonicalize_host_workspace",
        lambda value: host_path,
    )
    monkeypatch.setattr(
        broker.os,
        "getuid",
        lambda: 2002,
    )
    monkeypatch.setattr(
        broker.os,
        "getgid",
        lambda: 2004,
    )
    monkeypatch.setattr(
        broker,
        "_provision_sandbox_acl",
        lambda path, *, host_uid=None, host_gid=None: observed.append(
            ("provision", path)
        ),
    )
    monkeypatch.setattr(
        broker,
        "_remove_sandbox_acl",
        lambda path, *, host_uid=None, host_gid=None: observed.append(("remove", path)),
    )

    def fail_volume(
        volume_name: str,
        path: Path,
    ) -> None:
        raise RuntimeError("volume creation failed")

    monkeypatch.setattr(
        broker,
        "_create_host_backed_volume",
        fail_volume,
    )

    with pytest.raises(
        RuntimeError,
        match="volume creation failed",
    ):
        broker.create_workspace_grant(str(host_path))

    assert observed == [
        ("provision", host_path),
        ("remove", host_path),
    ]


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

    observed: dict[str, object] = {}

    monkeypatch.setattr(
        broker,
        "_run_acl_helper",
        lambda path, *, operation, host_uid=None, host_gid=None: observed.update(
            {
                "path": path,
                "operation": operation,
                "host_uid": host_uid,
                "host_gid": host_gid,
            }
        ),
    )

    broker._provision_sandbox_acl(
        tmp_path,
        host_uid=2000,
        host_gid=2001,
    )

    assert observed["path"] == tmp_path
    assert observed["operation"] == "provision-sandbox-acl"


def test_revoke_workspace_grant_uses_privileged_sandbox_acl_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "workspace-grants.json"
    host_path = tmp_path / "workspace"
    host_path.mkdir()
    grants_file.write_text(
        (
            "{\n"
            '  "ws_test": {\n'
            f'    "host_path": "{host_path}",\n'
            '    "host_gid": 2004,\n'
            '    "host_uid": 2003,\n'
            '    "read_only": false,\n'
            '    "target": "/workspace/project",\n'
            '    "volume_name": "mcp-ws-test"\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        broker.workspace_service,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    observed: dict[str, object] = {}

    def fake_remove(
        path: Path,
        *,
        host_uid: int | None = None,
        host_gid: int | None = None,
    ) -> None:
        observed["path"] = path
        observed["host_uid"] = host_uid
        observed["host_gid"] = host_gid

    monkeypatch.setattr(
        broker,
        "_remove_sandbox_acl_with_helper",
        fake_remove,
    )
    monkeypatch.setattr(
        broker,
        "_remove_volume",
        lambda volume_name: None,
    )

    result = broker.revoke_workspace_grant("ws_test")

    assert result["revoked"] is True
    assert observed["path"] == host_path.resolve()
    assert observed["host_uid"] == 2003
    assert observed["host_gid"] == 2004
