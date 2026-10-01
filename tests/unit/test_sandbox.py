from __future__ import annotations

import json

import pytest

from local_mcp_server.sandbox import policy
from local_mcp_server.sandbox import service


def test_default_memory_quantity_is_open_shell_compatible() -> None:
    assert policy.DEFAULT_MEMORY == "1Gi"


def test_memory_quantity_accepts_open_shell_binary_units() -> None:
    for value in (
        "512Mi",
        "1Gi",
        "2.5Gi",
        "8G",
    ):
        assert (
            policy.validate_memory(value)
            == value
        )


def test_memory_quantity_rejects_gib_suffix() -> None:
    with pytest.raises(
        ValueError,
        match="memory must be a quantity",
    ):
        policy.validate_memory(
            "1GiB"
        )


def test_build_sandbox_spec_emits_volume_mount_and_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "get_workspace_grant",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "host_path": "/tmp/test-workspace",
            "volume_name": "mcp-ws-testvolume123",
            "target": "/workspace/project",
            "read_only": False,
        },
    )

    spec = policy.build_sandbox_spec(
        "ws_test"
    )

    assert (
        spec.template.image
        == policy.SANDBOX_IMAGE
    )

    assert (
        spec.template.resources["limits"]["memory"]
        == "1Gi"
    )

    assert (
        spec.template.resources["limits"]["cpu"]
        == policy.DEFAULT_CPU
    )

    docker_config = (
        spec.template.driver_config["docker"]
    )

    assert len(
        docker_config["mounts"]
    ) == 1

    mount = docker_config["mounts"][0]

    assert mount["type"] == "volume"
    assert mount["source"] == "mcp-ws-testvolume123"
    assert mount["target"] == "/workspace/project"
    assert mount["read_only"] is False

    assert spec.policy.version == 1
    assert (
        spec.policy.filesystem.include_workdir
        is True
    )

    assert list(
        spec.policy.filesystem.read_only
    ) == [
        "/bin",
        "/usr",
        "/lib",
        "/proc",
        "/dev/urandom",
        "/etc",
        "/var/log",
    ]

    assert list(
        spec.policy.filesystem.read_write
    ) == [
        "/tmp",
        "/dev/null",
        "/workspace/project",
    ]

    assert (
        spec.policy.landlock.compatibility
        == "hard_requirement"
    )


def test_host_workspace_metadata_does_not_expose_host_path_or_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "get_workspace_grant",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "host_path": "/home/user/private-repository",
            "volume_name": "mcp-ws-secret-volume",
            "target": "/workspace/project",
            "read_only": False,
        },
    )

    metadata = service._host_workspace_metadata(
        "ws_test"
    )

    assert metadata == {
        "workspace_id": "ws_test",
        "authorized": True,
        "target": "/workspace/project",
        "read_only": False,
    }

    assert "host_path" not in metadata
    assert "volume_name" not in metadata


def test_sandbox_to_dict_does_not_expose_host_path_or_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "get_workspace_grant",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "host_path": "/home/user/private-repository",
            "volume_name": "mcp-ws-secret-volume",
            "target": "/workspace/project",
            "read_only": False,
        },
    )

    class Sandbox:
        id = "sandbox-id"
        name = "test-sandbox"
        phase = "running"
        status = type(
            "Status",
            (),
            {"phase": "running"},
        )()
        labels = {
            service.HOST_WORKSPACE_LABEL: "ws_test",
        }

    result = service._sandbox_to_dict(
        Sandbox()
    )

    metadata = result["host_workspace"]

    assert metadata == {
        "workspace_id": "ws_test",
        "authorized": True,
        "target": "/workspace/project",
        "read_only": False,
    }

    serialized = json.dumps(
        result
    )

    assert "/home/user/private-repository" not in serialized
    assert "mcp-ws-secret-volume" not in serialized


def test_create_sandbox_rejects_arbitrary_host_path() -> None:
    with pytest.raises(
        ValueError,
        match="workspace_id has an invalid format",
    ):
        service.create_sandbox(
            "test-sandbox",
            "/tmp/arbitrary/host/path",
        )


def test_create_sandbox_rejects_invalid_workspace_id() -> None:
    with pytest.raises(
        ValueError,
        match="workspace_id must not be empty",
    ):
        service.create_sandbox(
            "test-sandbox",
            "",
        )

    with pytest.raises(
        ValueError,
        match="workspace_id has an invalid format",
    ):
        service.create_sandbox(
            "test-sandbox",
            "invalid_prefix_123",
        )


def test_create_sandbox_rejects_nonexistent_workspace_id() -> None:
    with pytest.raises(
        ValueError,
        match="was not found",
    ):
        service.create_sandbox(
            "test-sandbox",
            "ws_nonexistent_capability",
        )