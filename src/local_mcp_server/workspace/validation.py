from __future__ import annotations

from pathlib import Path


def canonicalize_host_workspace(
    host_path: str,
) -> Path:
    """
    Canonicalize and validate a host workspace path.

    This function is a host-side authorization boundary and must be
    executed by the workspace broker, not by the MCP container.
    """
    if not isinstance(host_path, str) or not host_path.strip():
        raise ValueError("host_path must not be empty.")

    candidate = Path(host_path).expanduser()

    if not candidate.is_absolute():
        raise ValueError("host_path must be an absolute host filesystem path.")

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("host_path does not exist.") from exc
    except OSError as exc:
        raise ValueError("host_path could not be resolved.") from exc

    if not resolved.is_dir():
        raise ValueError("host_path must refer to a directory.")

    if resolved == Path("/"):
        raise ValueError("Mounting the host filesystem root is not allowed.")

    forbidden = (
        Path("/proc"),
        Path("/sys"),
        Path("/dev"),
        Path("/run"),
        Path("/etc"),
        Path("/var/run"),
        Path("/var/lib/docker"),
    )

    for path in forbidden:
        try:
            resolved.relative_to(path)
        except ValueError:
            continue

        raise ValueError(f"Mounting host path '{resolved}' is not allowed.")

    return resolved
