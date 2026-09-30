from __future__ import annotations

from pathlib import Path

import pytest

from local_mcp_server import sandbox


def test_default_memory_quantity_is_open_shell_compatible() -> None:
    assert sandbox.DEFAULT_MEMORY == "1Gi"


def test_memory_quantity_accepts_open_shell_binary_units() -> None:
    for value in ("512Mi", "1Gi", "2.5Gi", "8G"):
        assert sandbox._validate_memory(value) == value


def test_memory_quantity_rejects_gib_suffix() -> None:
    with pytest.raises(
        ValueError,
        match="memory must be a quantity",
    ):
        sandbox._validate_memory("1GiB")


def test_build_sandbox_spec_uses_valid_memory_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox,
        "resolve_workspace_grant",
        lambda workspace_id: tmp_path,
    )

    spec = sandbox._build_sandbox_spec(
        "ws_test",
    )

    assert spec.template.image == sandbox.SANDBOX_IMAGE
    assert (
        spec.template.resources["limits"]["memory"]
        == "1Gi"
    )
    assert (
        spec.template.resources["limits"]["cpu"]
        == sandbox.DEFAULT_CPU
    )

    docker_config = spec.template.driver_config["docker"]

    assert len(docker_config["mounts"]) == 1

    mount = docker_config["mounts"][0]

    assert mount["type"] == "bind"
    assert mount["source"] == str(tmp_path)
    assert mount["target"] == "/workspace/project"
    assert mount["read_only"] is False