from __future__ import annotations

import binascii
import struct
import zlib

import pytest
from mcp.server import MCPServer

from local_mcp_server.clone.tools import register_tools
from local_mcp_server.clone.visual import (
    _decode_png,
    _safe_artifact_relative_path,
    compare_png_bytes,
)


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _rgba_png(width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    assert len(pixels) == height
    assert all(len(row) == width for row in pixels)
    scanlines = bytearray()
    for row in pixels:
        scanlines.append(0)
        for pixel in row:
            scanlines.extend(pixel)
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(scanlines)))
        + _chunk(b"IEND", b"")
    )


def test_identical_pngs_pass_with_zero_error() -> None:
    image = _rgba_png(2, 1, [[(10, 20, 30, 255), (40, 50, 60, 255)]])
    result = compare_png_bytes(image, image)
    assert result["status"] == "pass"
    assert result["pixels_compared"] == 2
    assert result["mean_absolute_error"] == 0
    assert result["changed_pixel_ratio"] == 0


def test_changed_pixels_fail_when_ratio_threshold_is_exceeded() -> None:
    reference = _rgba_png(2, 1, [[(0, 0, 0, 255), (0, 0, 0, 255)]])
    candidate = _rgba_png(2, 1, [[(255, 255, 255, 255), (0, 0, 0, 255)]])
    result = compare_png_bytes(
        reference,
        candidate,
        pixel_threshold=16,
        max_changed_pixel_ratio=0.49,
        max_mean_absolute_error=255,
    )
    assert result["status"] == "fail"
    assert result["reason"] == "threshold_exceeded"
    assert result["changed_pixels"] == 1
    assert result["changed_pixel_ratio"] == 0.5


def test_dimension_mismatch_fails() -> None:
    reference = _rgba_png(1, 1, [[(0, 0, 0, 255)]])
    candidate = _rgba_png(2, 1, [[(0, 0, 0, 255), (0, 0, 0, 255)]])
    result = compare_png_bytes(reference, candidate)
    assert result["status"] == "fail"
    assert result["reason"] == "dimension_mismatch"
    assert result["pixels_compared"] == 0
    assert result["mean_absolute_error"] is None


def test_transparent_rgb_values_do_not_create_false_differences() -> None:
    reference = _rgba_png(1, 1, [[(255, 0, 0, 0)]])
    candidate = _rgba_png(1, 1, [[(0, 255, 0, 0)]])
    result = compare_png_bytes(reference, candidate)
    assert result["status"] == "pass"
    assert result["mean_absolute_error"] == 0


def test_png_decoder_returns_dimensions_and_rgb() -> None:
    image = _rgba_png(2, 1, [[(1, 2, 3, 255), (4, 5, 6, 255)]])
    width, height, rgb = _decode_png(image)
    assert (width, height) == (2, 1)
    assert rgb == bytes([1, 2, 3, 4, 5, 6])


def test_png_decoder_rejects_invalid_signature() -> None:
    with pytest.raises(ValueError, match="not a PNG"):
        _decode_png(b"not an image")


def test_png_decoder_rejects_bad_checksum() -> None:
    image = bytearray(_rgba_png(1, 1, [[(1, 2, 3, 255)]]))
    image[-1] ^= 1
    with pytest.raises(ValueError, match="checksum"):
        _decode_png(bytes(image))


def test_png_decoder_rejects_excessive_dimensions() -> None:
    header = struct.pack(">IIBBBBB", 3000, 3000, 8, 6, 0, 0, 0)
    image = _PNG_SIGNATURE + _chunk(b"IHDR", header)
    with pytest.raises(ValueError, match="pixel limit"):
        _decode_png(image)


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "../outside.png",
        "/tmp/outside.png",
        "images/../outside.png",
        r"images\outside.png",
        "images//outside.png",
        "images/\x00outside.png",
    ],
)
def test_artifact_paths_reject_unsafe_values(path: str) -> None:
    with pytest.raises(ValueError):
        _safe_artifact_relative_path(path, field="test_path")


def test_artifact_path_accepts_canonical_relative_path() -> None:
    assert _safe_artifact_relative_path(
        "research/visual-comparison/reference.png",
        field="test_path",
    ) == "research/visual-comparison/reference.png"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pixel_threshold": -1},
        {"pixel_threshold": 256},
        {"pixel_threshold": True},
        {"max_changed_pixel_ratio": -0.1},
        {"max_changed_pixel_ratio": 1.1},
        {"max_mean_absolute_error": float("nan")},
        {"max_mean_absolute_error": 256},
    ],
)
def test_comparison_rejects_invalid_thresholds(kwargs: dict[str, object]) -> None:
    image = _rgba_png(1, 1, [[(0, 0, 0, 255)]])
    with pytest.raises(ValueError):
        compare_png_bytes(image, image, **kwargs)


def test_visual_tools_are_registered() -> None:
    server = MCPServer("visual-tools-test")
    register_tools(server)
    for name in (
        "capture_screenshot_artifact",
        "compare_screenshot_artifacts",
        "verify_clone_with_visual",
    ):
        assert server._tool_manager.get_tool(name) is not None
