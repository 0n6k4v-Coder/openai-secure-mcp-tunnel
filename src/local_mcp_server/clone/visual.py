from __future__ import annotations

import base64
import binascii
import math
import posixpath
import struct
import uuid
import zlib
from typing import Any

from ..infrastructure.openshell.sandbox import execute_sandbox_argv
from ..sandbox.policy import validate_name
from .chrome import _run, validate_page_id
from .pipeline import (
    _PROJECT_ROOT,
    _safe_relative_project_path,
    verify_clone as verify_clone_impl,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
_MAX_PIXELS = 8_000_000


def _safe_artifact_relative_path(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be a non-empty relative path.")
    raw = value.strip()
    if raw.startswith("/") or "\\" in raw:
        raise ValueError(f"{field} must be a relative path.")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ValueError(f"{field} must not contain traversal or empty path segments.")
    normalized = _safe_relative_project_path(raw, field=field)
    if normalized != raw:
        raise ValueError(f"{field} must be a canonical relative path.")
    return normalized


def _remote_artifact_path(value: str, *, field: str) -> tuple[str, str]:
    relative = _safe_artifact_relative_path(value, field=field)
    return relative, f"{_PROJECT_ROOT}/{relative}"


def _sandbox_command(
    sandbox_name: str,
    argv: list[str],
    *,
    timeout_seconds: int = 15,
) -> dict[str, object]:
    result = execute_sandbox_argv(
        validate_name(sandbox_name),
        argv,
        timeout_seconds=timeout_seconds,
    )
    if int(result.get("return_code", 1)) != 0:
        detail = str(result.get("stderr") or result.get("stdout") or "").strip()
        raise RuntimeError(
            f"Sandbox command failed ({argv[0]}): {detail[:400] or 'unknown error'}"
        )
    return result


def _ensure_safe_parent(sandbox_name: str, remote_path: str) -> None:
    parent = posixpath.dirname(remote_path)
    _sandbox_command(sandbox_name, ["mkdir", "-p", parent])
    resolved = _sandbox_command(sandbox_name, ["realpath", "-e", parent])
    if str(resolved.get("stdout", "")).strip() != parent:
        raise ValueError("Screenshot directory resolves through a symlink.")


def _assert_destination_absent(sandbox_name: str, remote_path: str) -> None:
    result = execute_sandbox_argv(
        validate_name(sandbox_name),
        [
            "sh",
            "-c",
            '[ ! -e "$1" ] && [ ! -L "$1" ]',
            "sh",
            remote_path,
        ],
        timeout_seconds=10,
    )
    if int(result.get("return_code", 1)) != 0:
        raise FileExistsError("Screenshot destination already exists; choose a new path.")


def _remove_artifact(sandbox_name: str, remote_path: str) -> None:
    try:
        execute_sandbox_argv(
            validate_name(sandbox_name),
            ["rm", "-f", "--", remote_path],
            timeout_seconds=10,
        )
    except Exception:
        pass


def _read_artifact_bytes(sandbox_name: str, relative_path: str) -> bytes:
    _, remote_path = _remote_artifact_path(relative_path, field="screenshot_path")
    resolved = _sandbox_command(sandbox_name, ["realpath", "-e", remote_path])
    if str(resolved.get("stdout", "")).strip() != remote_path:
        raise ValueError("Screenshot path resolves through a symlink.")

    size_result = _sandbox_command(sandbox_name, ["stat", "-c", "%s", remote_path])
    try:
        size = int(str(size_result.get("stdout", "")).strip())
    except ValueError as exc:
        raise ValueError("Could not determine screenshot file size.") from exc
    if not 1 <= size <= _MAX_SCREENSHOT_BYTES:
        raise ValueError(f"Screenshot must be between 1 and {_MAX_SCREENSHOT_BYTES} bytes.")

    encoded_result = _sandbox_command(
        sandbox_name,
        ["base64", "-w", "0", remote_path],
        timeout_seconds=30,
    )
    encoded = encoded_result.get("stdout", "")
    if not isinstance(encoded, str):
        raise ValueError("Screenshot base64 data was invalid.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Screenshot base64 data was invalid.") from exc
    if len(data) != size:
        raise ValueError("Screenshot size changed while it was being read.")
    return data


def capture_screenshot_artifact(
    sandbox_name: str,
    page_id: int,
    output_path: str,
    *,
    full_page: bool = False,
) -> dict[str, Any]:
    """Capture a PNG from an existing page into a new relative workspace path."""
    name = validate_name(sandbox_name)
    page_id = validate_page_id(page_id)
    relative_path, remote_path = _remote_artifact_path(output_path, field="output_path")
    if not relative_path.lower().endswith(".png"):
        raise ValueError("Screenshot output_path must end with .png.")

    _ensure_safe_parent(name, remote_path)
    _assert_destination_absent(name, remote_path)
    args = [str(page_id), "--filePath", remote_path, "--format", "png"]
    if full_page:
        args.extend(["--fullPage", "true"])

    try:
        _run(name, "take_screenshot", args)
        data = _read_artifact_bytes(name, relative_path)
        width, height, _ = _decode_png(data)
    except Exception:
        _remove_artifact(name, remote_path)
        raise

    return {
        "status": "captured",
        "sandbox_name": name,
        "page_id": page_id,
        "path": relative_path,
        "mime_type": "image/png",
        "bytes": len(data),
        "width": width,
        "height": height,
        "full_page": full_page,
    }


def _paeth_predictor(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (abs(estimate - left), abs(estimate - above), abs(estimate - upper_left))
    return (left, above, upper_left)[distances.index(min(distances))]


def _decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Decode bounded, non-interlaced 8-bit RGB/RGBA PNG screenshots."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("PNG data must be non-empty bytes.")
    if len(data) > _MAX_SCREENSHOT_BYTES:
        raise ValueError("PNG exceeds the maximum allowed file size.")
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("Screenshot is not a PNG image.")

    offset = len(_PNG_SIGNATURE)
    width = height = 0
    channels = 0
    seen_ihdr = seen_idat = seen_iend = idat_closed = False
    idat_parts: list[bytes] = []
    idat_size = 0

    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("PNG contains a truncated chunk.")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        chunk_end = payload_end + 4
        if length > _MAX_SCREENSHOT_BYTES or chunk_end > len(data):
            raise ValueError("PNG contains an invalid chunk length.")
        payload = data[payload_start:payload_end]
        expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        if (binascii.crc32(kind + payload) & 0xFFFFFFFF) != expected_crc:
            raise ValueError("PNG chunk checksum did not match.")
        if not seen_ihdr and kind != b"IHDR":
            raise ValueError("PNG must begin with an IHDR chunk.")
        if seen_idat and kind != b"IDAT":
            idat_closed = True

        if kind == b"IHDR":
            if seen_ihdr or offset != len(_PNG_SIGNATURE) or length != 13:
                raise ValueError("PNG IHDR chunk is invalid.")
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if width < 1 or height < 1 or width * height > _MAX_PIXELS:
                raise ValueError(f"PNG dimensions exceed the {_MAX_PIXELS}-pixel limit.")
            if bit_depth != 8 or color_type not in {2, 6}:
                raise ValueError("Only 8-bit RGB and RGBA PNG screenshots are supported.")
            if compression != 0 or filtering != 0 or interlace != 0:
                raise ValueError("PNG uses an unsupported compression or interlace mode.")
            channels = 3 if color_type == 2 else 4
            seen_ihdr = True
        elif kind == b"IDAT":
            if idat_closed:
                raise ValueError("PNG IDAT chunks must be consecutive.")
            seen_idat = True
            idat_size += len(payload)
            if idat_size > _MAX_SCREENSHOT_BYTES:
                raise ValueError("PNG compressed data exceeds the size limit.")
            idat_parts.append(payload)
        elif kind == b"IEND":
            if length != 0 or not seen_idat:
                raise ValueError("PNG IEND chunk is invalid.")
            seen_iend = True
            offset = chunk_end
            break
        elif kind not in {b"PLTE", b"tRNS"} and (kind[0] & 0x20) == 0:
            raise ValueError("PNG contains an unsupported critical chunk.")
        offset = chunk_end

    if not seen_ihdr or not seen_idat or not seen_iend or offset != len(data):
        raise ValueError("PNG is incomplete or contains trailing data.")

    row_bytes = width * channels
    expected_size = height * (row_bytes + 1)
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(b"".join(idat_parts), expected_size + 1)
        if len(raw) > expected_size or decompressor.unconsumed_tail:
            raise ValueError("PNG expands beyond its declared dimensions.")
        # A bounded second read prevents flush() from expanding an oversized stream.
        remaining = expected_size + 1 - len(raw)
        raw += decompressor.decompress(b"", remaining)
        if len(raw) > expected_size or decompressor.unconsumed_tail:
            raise ValueError("PNG expands beyond its declared dimensions.")
        if not decompressor.eof or decompressor.unused_data:
            raise ValueError("PNG compressed stream is incomplete or contains extra data.")
    except zlib.error as exc:
        raise ValueError("PNG image data could not be decompressed.") from exc
    if len(raw) != expected_size:
        raise ValueError("PNG decompressed data length does not match its dimensions.")

    rgb = bytearray(width * height * 3)
    previous = bytearray(row_bytes)
    src = dst = 0
    for _ in range(height):
        filter_type = raw[src]
        src += 1
        scanline = bytearray(raw[src : src + row_bytes])
        src += row_bytes
        if filter_type not in {0, 1, 2, 3, 4}:
            raise ValueError("PNG uses an unsupported scanline filter.")
        for index in range(row_bytes):
            left = scanline[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            else:
                predictor = _paeth_predictor(left, above, upper_left)
            scanline[index] = (scanline[index] + predictor) & 0xFF

        if channels == 3:
            rgb[dst : dst + width * 3] = scanline
            dst += width * 3
        else:
            for index in range(0, row_bytes, 4):
                red, green, blue, alpha = scanline[index : index + 4]
                rgb[dst] = (red * alpha + 255 * (255 - alpha) + 127) // 255
                rgb[dst + 1] = (green * alpha + 255 * (255 - alpha) + 127) // 255
                rgb[dst + 2] = (blue * alpha + 255 * (255 - alpha) + 127) // 255
                dst += 3
        previous = scanline
    return width, height, bytes(rgb)


def compare_png_bytes(
    reference_png: bytes,
    candidate_png: bytes,
    *,
    pixel_threshold: int = 16,
    max_changed_pixel_ratio: float = 0.05,
    max_mean_absolute_error: float = 8.0,
) -> dict[str, Any]:
    """Compare RGB pixels using a changed-pixel ratio and mean absolute error."""
    if isinstance(pixel_threshold, bool) or not isinstance(pixel_threshold, int) or not 0 <= pixel_threshold <= 255:
        raise ValueError("pixel_threshold must be an integer from 0 to 255.")
    if isinstance(max_changed_pixel_ratio, bool) or not isinstance(max_changed_pixel_ratio, (int, float)) or not math.isfinite(max_changed_pixel_ratio) or not 0 <= max_changed_pixel_ratio <= 1:
        raise ValueError("max_changed_pixel_ratio must be between 0 and 1.")
    if isinstance(max_mean_absolute_error, bool) or not isinstance(max_mean_absolute_error, (int, float)) or not math.isfinite(max_mean_absolute_error) or not 0 <= max_mean_absolute_error <= 255:
        raise ValueError("max_mean_absolute_error must be between 0 and 255.")

    ref_w, ref_h, ref_rgb = _decode_png(reference_png)
    cand_w, cand_h, cand_rgb = _decode_png(candidate_png)
    if (ref_w, ref_h) != (cand_w, cand_h):
        return {
            "status": "fail",
            "reason": "dimension_mismatch",
            "reference_width": ref_w,
            "reference_height": ref_h,
            "candidate_width": cand_w,
            "candidate_height": cand_h,
            "pixels_compared": 0,
            "mean_absolute_error": None,
            "changed_pixel_ratio": 1.0,
            "pixel_threshold": pixel_threshold,
            "max_changed_pixel_ratio": float(max_changed_pixel_ratio),
            "max_mean_absolute_error": float(max_mean_absolute_error),
        }

    pixels = ref_w * ref_h
    error_sum = changed = 0
    for offset in range(0, len(ref_rgb), 3):
        errors = (
            abs(ref_rgb[offset] - cand_rgb[offset]),
            abs(ref_rgb[offset + 1] - cand_rgb[offset + 1]),
            abs(ref_rgb[offset + 2] - cand_rgb[offset + 2]),
        )
        error_sum += sum(errors)
        if max(errors) > pixel_threshold:
            changed += 1
    mean_error = error_sum / (pixels * 3)
    changed_ratio = changed / pixels
    passed = mean_error <= max_mean_absolute_error and changed_ratio <= max_changed_pixel_ratio
    return {
        "status": "pass" if passed else "fail",
        "reason": "within_thresholds" if passed else "threshold_exceeded",
        "width": ref_w,
        "height": ref_h,
        "pixels_compared": pixels,
        "mean_absolute_error": mean_error,
        "changed_pixels": changed,
        "changed_pixel_ratio": changed_ratio,
        "pixel_threshold": pixel_threshold,
        "max_changed_pixel_ratio": float(max_changed_pixel_ratio),
        "max_mean_absolute_error": float(max_mean_absolute_error),
    }


def compare_screenshot_artifacts(
    sandbox_name: str,
    reference_path: str,
    candidate_path: str,
    *,
    pixel_threshold: int = 16,
    max_changed_pixel_ratio: float = 0.05,
    max_mean_absolute_error: float = 8.0,
) -> dict[str, Any]:
    name = validate_name(sandbox_name)
    reference = _read_artifact_bytes(name, reference_path)
    candidate = _read_artifact_bytes(name, candidate_path)
    return {
        **compare_png_bytes(
            reference,
            candidate,
            pixel_threshold=pixel_threshold,
            max_changed_pixel_ratio=max_changed_pixel_ratio,
            max_mean_absolute_error=max_mean_absolute_error,
        ),
        "sandbox_name": name,
        "reference_path": _safe_artifact_relative_path(reference_path, field="reference_path"),
        "candidate_path": _safe_artifact_relative_path(candidate_path, field="candidate_path"),
    }


def verify_clone_with_visual(
    sandbox_name: str,
    reference_page_id: int,
    candidate_page_id: int,
    evidence: dict[str, Any] | None = None,
    *,
    output_dir: str = "research/visual-comparison",
    full_page: bool = False,
    pixel_threshold: int = 16,
    max_changed_pixel_ratio: float = 0.05,
    max_mean_absolute_error: float = 8.0,
) -> dict[str, Any]:
    """Capture two open pages, compare their pixels, and combine verification evidence."""
    name = validate_name(sandbox_name)
    reference_page_id = validate_page_id(reference_page_id)
    candidate_page_id = validate_page_id(candidate_page_id)
    if reference_page_id == candidate_page_id:
        raise ValueError("Reference and candidate must be different browser pages.")
    if evidence is None:
        evidence = {}
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object.")

    directory = _safe_artifact_relative_path(output_dir, field="output_dir")
    run_dir = posixpath.join(directory, uuid.uuid4().hex)
    reference_path = posixpath.join(run_dir, "reference.png")
    candidate_path = posixpath.join(run_dir, "candidate.png")
    reference_artifact = None
    candidate_artifact = None
    try:
        reference_artifact = capture_screenshot_artifact(name, reference_page_id, reference_path, full_page=full_page)
        candidate_artifact = capture_screenshot_artifact(name, candidate_page_id, candidate_path, full_page=full_page)
        comparison = compare_screenshot_artifacts(
            name,
            reference_path,
            candidate_path,
            pixel_threshold=pixel_threshold,
            max_changed_pixel_ratio=max_changed_pixel_ratio,
            max_mean_absolute_error=max_mean_absolute_error,
        )
    except Exception:
        if reference_artifact is not None:
            _remove_artifact(name, f"{_PROJECT_ROOT}/{reference_path}")
        if candidate_artifact is not None:
            _remove_artifact(name, f"{_PROJECT_ROOT}/{candidate_path}")
        raise

    verification = verify_clone_impl(**evidence)
    mismatches = verification.get("mismatches", [])
    if not isinstance(mismatches, list):
        mismatches = []
    if comparison["status"] == "fail":
        mismatches.append(f"Visual screenshot comparison failed: {comparison['reason']}.")

    verification["visual"] = {
        "status": comparison["status"],
        "reason": comparison["reason"],
        "mean_absolute_error": comparison.get("mean_absolute_error"),
        "changed_pixel_ratio": comparison.get("changed_pixel_ratio"),
        "reference_path": reference_path,
        "candidate_path": candidate_path,
    }
    verification["screenshot_comparison"] = comparison
    verification["artifacts"] = {
        "reference": reference_artifact,
        "candidate": candidate_artifact,
    }
    verification["mismatches"] = mismatches
    statuses = [
        verification.get("structural", {}).get("status"),
        verification.get("assets", {}).get("status"),
        comparison["status"],
        verification.get("behavior", {}).get("status"),
    ]
    if any(status == "fail" for status in statuses) or mismatches:
        verification["status"] = "failed"
    elif all(status == "pass" for status in statuses):
        verification["status"] = "passed"
    else:
        verification["status"] = "incomplete"
    return verification
