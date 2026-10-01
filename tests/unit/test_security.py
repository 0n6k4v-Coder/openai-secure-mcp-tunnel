from __future__ import annotations

import os
from pathlib import Path

import pytest

from local_mcp_server.workspace import broker as workspace_broker
from local_mcp_server.workspace import service as workspace_service
from local_mcp_server.workspace import validation as workspace_validation


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
            workspace_validation.canonicalize_host_workspace(
                str(path),
            )


def test_canonicalize_host_workspace_requires_absolute_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="absolute",
    ):
        workspace_validation.canonicalize_host_workspace(
            "relative/path",
        )

    missing = tmp_path / "missing"

    with pytest.raises(
        ValueError,
        match="does not exist",
    ):
        workspace_validation.canonicalize_host_workspace(
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
        workspace_validation.canonicalize_host_workspace(
            str(link),
        )
        == real.resolve()
    )


def test_create_workspace_grant_rejects_read_only_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workspace_broker,
        "GRANTS_READ_ONLY",
        True,
    )

    with pytest.raises(
        RuntimeError,
        match="read-only",
    ):
        workspace_broker.create_workspace_grant(
            str(tmp_path),
        )


def test_create_workspace_grant_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "grants.json"

    monkeypatch.setattr(
        workspace_service,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    monkeypatch.setattr(
        workspace_service,
        "GRANTS_READ_ONLY",
        False,
    )

    monkeypatch.setattr(
        workspace_broker,
        "GRANTS_READ_ONLY",
        False,
    )

    grant = workspace_broker.create_workspace_grant(
        str(tmp_path),
        create_volume=False,
    )

    assert grant["workspace_id"].startswith(
        "ws_",
    )

    assert grant["volume_name"].startswith(
        "mcp-ws-",
    )

    assert grant["target"] == "/workspace/project"
    assert grant["read_only"] is False
    assert grant["host_path"] == str(
        tmp_path.resolve(),
    )

    resolved_vol = workspace_service.resolve_workspace_grant(
        str(
            grant["workspace_id"],
        ),
    )

    assert resolved_vol == grant[
        "volume_name"
    ]


def test_list_workspace_grants_does_not_require_host_path_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "grants.json"

    grants_file.write_text(
        (
            '{\n'
            '  "ws_test123": {\n'
            '    "host_path": "/host/path/not-visible-in-container",\n'
            '    "volume_name": "mcp-ws-test123",\n'
            '    "target": "/workspace/project",\n'
            '    "read_only": false\n'
            '  }\n'
            '}\n'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        workspace_service,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    grants = workspace_service.list_workspace_grants()

    assert grants == [
        {
            "workspace_id": "ws_test123",
            "host_path": "/host/path/not-visible-in-container",
            "volume_name": "mcp-ws-test123",
            "target": "/workspace/project",
            "read_only": False,
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
            '  "ws_test123": {\n'
            '    "host_path": "/host/path/not-visible-in-container",\n'
            '    "volume_name": "mcp-ws-test123",\n'
            '    "target": "/workspace/project",\n'
            '    "read_only": false\n'
            '  }\n'
            '}\n'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        workspace_service,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    assert (
        workspace_service.resolve_workspace_grant(
            "ws_test123",
        )
        == "mcp-ws-test123"
    )


def test_resolve_workspace_grant_rejects_invalid_and_nonexistent_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "grants.json"

    grants_file.write_text(
        "{}",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        workspace_service,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    with pytest.raises(
        ValueError,
        match="workspace_id must not be empty",
    ):
        workspace_service.resolve_workspace_grant("")

    with pytest.raises(
        ValueError,
        match="workspace_id has an invalid format",
    ):
        workspace_service.resolve_workspace_grant(
            "invalid_prefix",
        )

    with pytest.raises(
        ValueError,
        match="was not found",
    ):
        workspace_service.resolve_workspace_grant(
            "ws_missing",
        )


def test_revoke_workspace_grant_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants_file = tmp_path / "grants.json"

    monkeypatch.setattr(
        workspace_service,
        "WORKSPACE_GRANTS_FILE",
        grants_file,
    )

    monkeypatch.setattr(
        workspace_service,
        "GRANTS_READ_ONLY",
        False,
    )

    monkeypatch.setattr(
        workspace_broker,
        "GRANTS_READ_ONLY",
        False,
    )

    grant = workspace_broker.create_workspace_grant(
        str(tmp_path),
        create_volume=False,
    )

    ws_id = str(
        grant["workspace_id"],
    )

    assert (
        workspace_service.resolve_workspace_grant(
            ws_id,
        )
        == grant["volume_name"]
    )

    revoked = workspace_broker.revoke_workspace_grant(
        ws_id,
        remove_volume=False,
    )

    assert revoked["revoked"] is True
    assert revoked["workspace_id"] == ws_id

    with pytest.raises(
        ValueError,
        match="was not found",
    ):
        workspace_service.resolve_workspace_grant(
            ws_id,
        )


def test_revoke_workspace_grant_rejects_read_only_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workspace_broker,
        "GRANTS_READ_ONLY",
        True,
    )

    with pytest.raises(
        RuntimeError,
        match="read-only",
    ):
        workspace_broker.revoke_workspace_grant(
            "ws_test",
        )