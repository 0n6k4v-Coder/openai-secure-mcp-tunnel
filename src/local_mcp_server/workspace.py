from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path
from threading import Lock


def _default_grants_file() -> Path:
    env_path = os.environ.get("WORKSPACE_GRANTS_FILE")
    if env_path:
        return Path(env_path).resolve()
    container_path = Path(
        "/var/lib/local-mcp-server/workspace-grants/workspace-grants.json"
    )
    if container_path.parent.exists():
        return container_path.resolve()
    project_root = Path(__file__).resolve().parents[2]
    return (
        project_root
        / ".state"
        / "workspace-grants"
        / "workspace-grants.json"
    ).resolve()


WORKSPACE_ROOT = Path(
    os.environ.get("WORKSPACE_DIR", "/app/workspace")
).resolve()

WORKSPACE_GRANTS_FILE = _default_grants_file()

MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 1_000_000

_GRANTS_LOCK = Lock()

GRANTS_READ_ONLY = os.environ.get(
    "WORKSPACE_GRANTS_READ_ONLY",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}


def _ensure_grants_directory() -> None:
    WORKSPACE_GRANTS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


def _load_workspace_grants() -> dict[str, dict[str, object]]:
    _ensure_grants_directory()

    if not WORKSPACE_GRANTS_FILE.exists():
        return {}

    try:
        data = json.loads(
            WORKSPACE_GRANTS_FILE.read_text(
                encoding="utf-8",
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Workspace grant database could not be read."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "Workspace grant database has an invalid format."
        )

    result: dict[str, dict[str, object]] = {}

    for workspace_id, entry in data.items():
        if not isinstance(workspace_id, str):
            continue

        if isinstance(entry, dict):
            host_path = entry.get("host_path")
            volume_name = entry.get("volume_name")
            target = entry.get("target", "/workspace/project")
            read_only = bool(entry.get("read_only", False))

            if isinstance(host_path, str) and isinstance(volume_name, str):
                result[workspace_id] = {
                    "host_path": host_path,
                    "volume_name": volume_name,
                    "target": (
                        target
                        if isinstance(target, str)
                        else "/workspace/project"
                    ),
                    "read_only": read_only,
                }
        elif isinstance(entry, str):
            result[workspace_id] = {
                "host_path": entry,
                "volume_name": "",
                "target": "/workspace/project",
                "read_only": False,
            }

    return result


def _save_workspace_grants(
    grants: dict[str, dict[str, object]],
) -> None:
    if GRANTS_READ_ONLY:
        raise RuntimeError(
            "Workspace grants are read-only in this process. "
            "Run the host workspace broker to authorize a workspace."
        )

    _ensure_grants_directory()

    temporary = WORKSPACE_GRANTS_FILE.with_suffix(
        WORKSPACE_GRANTS_FILE.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            grants,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    os.replace(
        temporary,
        WORKSPACE_GRANTS_FILE,
    )


def canonicalize_host_workspace(
    host_path: str,
) -> Path:
    """
    Canonicalize and validate a host workspace path.

    This function is a host-side authorization boundary and must be
    executed by the workspace broker, not by the MCP container.
    """
    if not isinstance(host_path, str) or not host_path.strip():
        raise ValueError(
            "host_path must not be empty."
        )

    candidate = Path(host_path).expanduser()

    if not candidate.is_absolute():
        raise ValueError(
            "host_path must be an absolute host filesystem path."
        )

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(
            "host_path does not exist."
        ) from exc
    except OSError as exc:
        raise ValueError(
            "host_path could not be resolved."
        ) from exc

    if not resolved.is_dir():
        raise ValueError(
            "host_path must refer to a directory."
        )

    if resolved == Path("/"):
        raise ValueError(
            "Mounting the host filesystem root is not allowed."
        )

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

        raise ValueError(
            f"Mounting host path '{resolved}' is not allowed."
        )

    return resolved


def _create_docker_volume(
    volume_name: str,
    canonical_host_path: str,
) -> None:
    cmd = [
        "docker",
        "volume",
        "create",
        "--driver",
        "local",
        "--opt",
        "type=none",
        "--opt",
        "o=bind",
        "--opt",
        f"device={canonical_host_path}",
        volume_name,
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(
            f"Failed to execute docker command: {exc}"
        ) from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to create Docker volume '{volume_name}': "
            f"{proc.stderr.strip()}"
        )


def _verify_docker_volume(
    volume_name: str,
) -> None:
    cmd = [
        "docker",
        "volume",
        "inspect",
        volume_name,
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(
            f"Failed to execute docker command: {exc}"
        ) from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"Docker volume '{volume_name}' could not be verified: "
            f"{proc.stderr.strip()}"
        )


def _remove_docker_volume(
    volume_name: str,
) -> None:
    cmd = [
        "docker",
        "volume",
        "rm",
        volume_name,
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        pass


def create_workspace_grant(
    host_path: str,
    create_volume: bool = True,
) -> dict[str, object]:
    """
    Create a capability representing one human-authorized host workspace.

    This function is intended for the host-only workspace broker.
    The MCP server process must run with
    WORKSPACE_GRANTS_READ_ONLY=true.
    """
    if GRANTS_READ_ONLY:
        raise RuntimeError(
            "Workspace grants are read-only in this process. "
            "Run the host workspace broker to authorize a workspace."
        )

    resolved = canonicalize_host_workspace(host_path)

    token = secrets.token_hex(12)
    workspace_id = f"ws_{token}"
    volume_name = f"mcp-ws-{token}"

    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

        while workspace_id in grants:
            token = secrets.token_hex(12)
            workspace_id = f"ws_{token}"
            volume_name = f"mcp-ws-{token}"

        if create_volume:
            _create_docker_volume(volume_name, str(resolved))
            _verify_docker_volume(volume_name)

        grants[workspace_id] = {
            "host_path": str(resolved),
            "volume_name": volume_name,
            "target": "/workspace/project",
            "read_only": False,
        }

        _save_workspace_grants(grants)

    return {
        "workspace_id": workspace_id,
        "host_path": str(resolved),
        "volume_name": volume_name,
        "target": "/workspace/project",
        "read_only": False,
    }


def revoke_workspace_grant(
    workspace_id: str,
    remove_volume: bool = True,
) -> dict[str, object]:
    """
    Revoke an authorized workspace capability and its associated Docker volume.

    This function is intended for the host-only workspace broker.
    The MCP server process must run with
    WORKSPACE_GRANTS_READ_ONLY=true.
    """
    if GRANTS_READ_ONLY:
        raise RuntimeError(
            "Workspace grants are read-only in this process. "
            "Run the host workspace broker to revoke a workspace."
        )

    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError(
            "workspace_id must not be empty."
        )

    if not workspace_id.startswith("ws_"):
        raise ValueError(
            "workspace_id has an invalid format."
        )

    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

        if workspace_id not in grants:
            raise ValueError(
                f"Workspace grant '{workspace_id}' was not found."
            )

        entry = grants.pop(workspace_id)
        _save_workspace_grants(grants)

    volume_name = entry.get("volume_name")
    if remove_volume and isinstance(volume_name, str) and volume_name:
        _remove_docker_volume(volume_name)

    return {
        "workspace_id": workspace_id,
        "revoked": True,
        "volume_name": volume_name,
    }


def resolve_workspace_grant(
    workspace_id: str,
) -> str:
    """
    Resolve an opaque workspace capability into its Docker volume name.

    No host filesystem access is attempted from the MCP container.
    """
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError(
            "workspace_id must not be empty."
        )

    if not workspace_id.startswith("ws_"):
        raise ValueError(
            "workspace_id has an invalid format."
        )

    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

    entry = grants.get(workspace_id)

    if entry is None:
        raise ValueError(
            f"Workspace grant '{workspace_id}' was not found."
        )

    volume_name = entry.get("volume_name")
    if not isinstance(volume_name, str) or not volume_name.strip():
        raise ValueError(
            f"Workspace grant '{workspace_id}' has no associated volume name."
        )

    return volume_name


def get_workspace_grant(
    workspace_id: str,
) -> dict[str, object]:
    """Get the full grant record for an authorized workspace capability."""
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError(
            "workspace_id must not be empty."
        )

    if not workspace_id.startswith("ws_"):
        raise ValueError(
            "workspace_id has an invalid format."
        )

    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

    entry = grants.get(workspace_id)
    if entry is None:
        raise ValueError(
            f"Workspace grant '{workspace_id}' was not found."
        )

    return {
        "workspace_id": workspace_id,
        "host_path": entry["host_path"],
        "volume_name": entry["volume_name"],
        "target": entry.get("target", "/workspace/project"),
        "read_only": bool(entry.get("read_only", False)),
    }


def list_workspace_grants() -> list[dict[str, object]]:
    """
    List broker-issued workspace capabilities.

    Grant records are returned exactly as stored by the host-side broker.
    No host filesystem access is attempted from the MCP container.
    """
    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

    result: list[dict[str, object]] = []

    for workspace_id, entry in sorted(grants.items()):
        if not workspace_id.startswith("ws_"):
            continue

        host_path = entry.get("host_path")
        volume_name = entry.get("volume_name")

        if not isinstance(host_path, str) or not host_path.startswith("/"):
            continue

        if not isinstance(volume_name, str) or not volume_name:
            continue

        result.append(
            {
                "workspace_id": workspace_id,
                "host_path": host_path,
                "volume_name": volume_name,
                "target": entry.get("target", "/workspace/project"),
                "read_only": bool(entry.get("read_only", False)),
            }
        )

    return result


def resolve_workspace_path(
    relative_path: str,
) -> Path:
    """Resolve a user-supplied path while enforcing the workspace boundary."""
    if not relative_path:
        raise ValueError(
            "Path must not be empty."
        )

    candidate = WORKSPACE_ROOT / relative_path
    resolved = candidate.resolve()

    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError(
            "Requested path is outside the workspace."
        ) from exc

    return resolved


def list_workspace_files() -> list[str]:
    """Return regular files below the workspace."""
    if not WORKSPACE_ROOT.exists():
        return []

    results: list[str] = []

    for path in WORKSPACE_ROOT.rglob("*"):
        try:
            resolved = path.resolve()

            if not resolved.is_file():
                continue

            resolved.relative_to(WORKSPACE_ROOT)

            results.append(
                resolved.relative_to(
                    WORKSPACE_ROOT
                ).as_posix()
            )

        except (OSError, ValueError):
            continue

    return sorted(results)


def read_workspace_text_file(
    relative_path: str,
) -> str:
    """Read a UTF-8 text file from the workspace."""
    target = resolve_workspace_path(relative_path)

    if not target.is_file():
        raise ValueError(
            "Requested path is not a regular file."
        )

    size = target.stat().st_size

    if size > MAX_READ_BYTES:
        raise ValueError(
            "Requested file is too large."
        )

    try:
        return target.read_text(
            encoding="utf-8",
        )
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Requested file is not valid UTF-8 text."
        ) from exc


def create_workspace_file(
    relative_path: str,
    content: str,
) -> str:
    """Create a new UTF-8 text file in the workspace."""
    requested = WORKSPACE_ROOT / relative_path

    if requested.is_symlink():
        raise ValueError(
            "Requested path must not be a symbolic link."
        )

    target = resolve_workspace_path(relative_path)

    if target.exists():
        raise ValueError(
            "A file or directory already exists at that path."
        )

    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        raise ValueError(
            "Content is too large."
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_text(
        content,
        encoding="utf-8",
    )

    return target.relative_to(
        WORKSPACE_ROOT
    ).as_posix()


def write_workspace_file(
    relative_path: str,
    content: str,
) -> str:
    """Replace the contents of an existing UTF-8 text file."""
    target = resolve_workspace_path(relative_path)

    if not target.is_file():
        raise ValueError(
            "Requested path is not a regular file."
        )

    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        raise ValueError(
            "Content is too large."
        )

    target.write_text(
        content,
        encoding="utf-8",
    )

    return target.relative_to(
        WORKSPACE_ROOT
    ).as_posix()


def create_workspace_directory(
    relative_path: str,
) -> str:
    """Create a directory inside the workspace."""
    target = resolve_workspace_path(relative_path)

    if target.exists():
        raise ValueError(
            "A file or directory already exists at that path."
        )

    target.mkdir(
        parents=True,
        exist_ok=False,
    )

    return target.relative_to(
        WORKSPACE_ROOT
    ).as_posix()


def rename_workspace_path(
    relative_path: str,
    new_relative_path: str,
) -> str:
    """Rename a file or directory within the workspace."""
    source = resolve_workspace_path(relative_path)
    destination = resolve_workspace_path(new_relative_path)

    if not source.exists():
        raise ValueError(
            "Source path does not exist."
        )

    if destination.exists():
        raise ValueError(
            "Destination path already exists."
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source.rename(destination)

    return destination.relative_to(
        WORKSPACE_ROOT
    ).as_posix()


def delete_workspace_file(
    relative_path: str,
) -> str:
    """Delete a regular file inside the workspace."""
    target = resolve_workspace_path(relative_path)

    if not target.is_file():
        raise ValueError(
            "Requested path is not a regular file."
        )

    target.unlink()

    return target.relative_to(
        WORKSPACE_ROOT
    ).as_posix()


def delete_workspace_directory(
    relative_path: str,
) -> str:
    """Delete a directory tree inside the workspace."""
    if not relative_path:
        raise ValueError(
            "Path must not be empty."
        )

    requested = WORKSPACE_ROOT / relative_path

    if requested == WORKSPACE_ROOT:
        raise ValueError(
            "Deleting the workspace root is not allowed."
        )

    if requested.is_symlink():
        raise ValueError(
            "Requested path must not be a symbolic link."
        )

    target = requested.resolve()

    try:
        target.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError(
            "Requested path is outside the workspace."
        ) from exc

    if target == WORKSPACE_ROOT:
        raise ValueError(
            "Deleting the workspace root is not allowed."
        )

    if not target.exists():
        raise ValueError(
            "Requested directory does not exist."
        )

    if not target.is_dir():
        raise ValueError(
            "Requested path is not a directory."
        )

    shutil.rmtree(target)

    return target.relative_to(
        WORKSPACE_ROOT
    ).as_posix()