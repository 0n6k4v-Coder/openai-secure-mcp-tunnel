from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from threading import Lock

from ..config.paths import workspace_grants_file


def _default_grants_file() -> Path:
    env_path = os.environ.get("WORKSPACE_GRANTS_FILE")

    if env_path:
        return Path(env_path).resolve()

    container_path = Path(
        "/var/lib/local-mcp-server/workspace-grants/workspace-grants.json"
    )

    if os.environ.get("MCP_RUNTIME", "default") == "default" and container_path.parent.exists():
        return container_path.resolve()

    return workspace_grants_file().resolve()


WORKSPACE_GRANTS_FILE = _default_grants_file()

_GRANTS_LOCK = Lock()

GRANTS_READ_ONLY = os.environ.get(
    "WORKSPACE_GRANTS_READ_ONLY",
    "false",
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _grants_file() -> Path:
    """
    Return the current grants database path.

    The service module's value is authoritative so tests and runtime
    configuration can replace WORKSPACE_GRANTS_FILE directly.
    """
    return Path(WORKSPACE_GRANTS_FILE)


def _ensure_grants_directory() -> None:
    grants_directory = _grants_file().parent

    grants_directory.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    mode = stat.S_IMODE(grants_directory.stat().st_mode)

    if mode & 0o077:
        raise RuntimeError(
            "Workspace grants directory must not be accessible by group or other users."
        )


def _load_workspace_grants() -> dict[str, dict[str, object]]:
    _ensure_grants_directory()

    grants_file = _grants_file()

    if not grants_file.exists():
        return {}

    try:
        data = json.loads(
            grants_file.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError("Workspace grant database could not be read.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Workspace grant database has an invalid format.")

    result: dict[str, dict[str, object]] = {}

    for workspace_id, entry in data.items():
        if not isinstance(workspace_id, str):
            continue

        if isinstance(entry, dict):
            host_path = entry.get("host_path")
            volume_name = entry.get("volume_name")
            target = entry.get(
                "target",
                "/workspace/project",
            )
            read_only = bool(
                entry.get(
                    "read_only",
                    False,
                )
            )

            if isinstance(host_path, str) and isinstance(volume_name, str):
                result[workspace_id] = {
                    "host_path": host_path,
                    "volume_name": volume_name,
                    "target": (
                        target if isinstance(target, str) else "/workspace/project"
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

    grants_file = _grants_file()
    temporary = grants_file.with_suffix(grants_file.suffix + ".tmp")

    temporary.write_text(
        json.dumps(
            grants,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    os.chmod(temporary, 0o600)

    os.replace(
        temporary,
        grants_file,
    )

    os.chmod(grants_file, 0o600)


def resolve_workspace_grant(
    workspace_id: str,
) -> str:
    """
    Resolve an opaque workspace capability into its Docker volume name.

    No host filesystem access is attempted from the MCP container.
    """
    if (
        not isinstance(
            workspace_id,
            str,
        )
        or not workspace_id.strip()
    ):
        raise ValueError("workspace_id must not be empty.")

    if not workspace_id.startswith("ws_"):
        raise ValueError("workspace_id has an invalid format.")

    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

    entry = grants.get(workspace_id)

    if entry is None:
        raise ValueError(f"Workspace grant '{workspace_id}' was not found.")

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
    if (
        not isinstance(
            workspace_id,
            str,
        )
        or not workspace_id.strip()
    ):
        raise ValueError("workspace_id must not be empty.")

    if not workspace_id.startswith("ws_"):
        raise ValueError("workspace_id has an invalid format.")

    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

    entry = grants.get(workspace_id)

    if entry is None:
        raise ValueError(f"Workspace grant '{workspace_id}' was not found.")

    return {
        "workspace_id": workspace_id,
        "host_path": entry["host_path"],
        "volume_name": entry["volume_name"],
        "target": entry.get(
            "target",
            "/workspace/project",
        ),
        "read_only": bool(
            entry.get(
                "read_only",
                False,
            )
        ),
    }


def list_workspace_grants() -> list[dict[str, object]]:
    """
    List broker-issued workspace capabilities.

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
                "target": entry.get(
                    "target",
                    "/workspace/project",
                ),
                "read_only": bool(
                    entry.get(
                        "read_only",
                        False,
                    )
                ),
            }
        )

    return result
