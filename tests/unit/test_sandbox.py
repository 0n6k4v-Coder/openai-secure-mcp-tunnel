from __future__ import annotations

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