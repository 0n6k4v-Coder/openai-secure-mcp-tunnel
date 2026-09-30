from __future__ import annotations

from local_mcp_server import sandbox


def test_default_memory_quantity_is_open_shell_compatible() -> None:
    assert sandbox.DEFAULT_MEMORY == "1Gi"


def test_memory_quantity_accepts_open_shell_binary_units() -> None:
    for value in ("512Mi", "1Gi", "2.5Gi", "8G"):
        assert sandbox._validate_memory(value) == value


def test_memory_quantity_rejects_gib_suffix() -> None:
    with __import__("pytest").raises(
        ValueError,
        match="memory must be a quantity",
    ):
        sandbox._validate_memory("1GiB")


def test_build_sandbox_spec_uses_valid_memory_limit() -> None:
    spec = sandbox._build_sandbox_spec()

    assert spec.template.image == sandbox.SANDBOX_IMAGE
    assert spec.template.resources["limits"]["memory"] == "1Gi"
    assert spec.template.resources["limits"]["cpu"] == sandbox.DEFAULT_CPU
