from __future__ import annotations

import secrets
import subprocess

from . import service as _service
from .service import (
    _GRANTS_LOCK,
    _load_workspace_grants,
    _save_workspace_grants,
)
from .validation import canonicalize_host_workspace


GRANTS_READ_ONLY = _service.GRANTS_READ_ONLY


def _grants_read_only() -> bool:
    """Return the broker's current workspace-grant write policy."""
    return bool(
        GRANTS_READ_ONLY
    )


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
    if _grants_read_only():
        raise RuntimeError(
            "Workspace grants are read-only in this process. "
            "Run the host workspace broker to authorize a workspace."
        )

    resolved = canonicalize_host_workspace(
        host_path
    )

    token = secrets.token_hex(
        12
    )

    workspace_id = f"ws_{token}"
    volume_name = f"mcp-ws-{token}"

    with _GRANTS_LOCK:
        grants = _load_workspace_grants()

        while workspace_id in grants:
            token = secrets.token_hex(
                12
            )
            workspace_id = f"ws_{token}"
            volume_name = f"mcp-ws-{token}"

        if create_volume:
            _create_docker_volume(
                volume_name,
                str(resolved),
            )
            _verify_docker_volume(
                volume_name
            )

        grants[workspace_id] = {
            "host_path": str(resolved),
            "volume_name": volume_name,
            "target": "/workspace/project",
            "read_only": False,
        }

        _save_workspace_grants(
            grants
        )

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
    """
    if _grants_read_only():
        raise RuntimeError(
            "Workspace grants are read-only in this process. "
            "Run the host workspace broker to revoke a workspace."
        )

    if not isinstance(
        workspace_id,
        str,
    ) or not workspace_id.strip():
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

        entry = grants.pop(
            workspace_id
        )

        _save_workspace_grants(
            grants
        )

    volume_name = entry.get(
        "volume_name"
    )

    if (
        remove_volume
        and isinstance(volume_name, str)
        and volume_name
    ):
        _remove_docker_volume(
            volume_name
        )

    return {
        "workspace_id": workspace_id,
        "revoked": True,
        "volume_name": volume_name,
    }


def main(
    argv: list[str] | None = None,
) -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="workspace-broker",
        description=(
            "Host-only workspace authorization broker. "
            "Run this command on the host, never as an MCP tool."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    authorize = subparsers.add_parser(
        "authorize",
        help="Authorize one host directory for sandbox use.",
    )

    authorize.add_argument(
        "host_path",
        help="Absolute host directory selected by the human operator.",
    )

    revoke = subparsers.add_parser(
        "revoke",
        help="Revoke an authorized workspace capability.",
    )

    revoke.add_argument(
        "workspace_id",
        help="Opaque capability ID (e.g. ws_...) to revoke.",
    )

    subparsers.add_parser(
        "list",
        help="List currently authorized workspace capabilities.",
    )

    try:
        args = parser.parse_args(
            argv
        )

        if args.command == "authorize":
            result = create_workspace_grant(
                args.host_path
            )

        elif args.command == "revoke":
            result = revoke_workspace_grant(
                args.workspace_id
            )

        elif args.command == "list":
            from .service import list_workspace_grants

            result = list_workspace_grants()

        else:
            parser.error(
                f"unsupported command: {args.command}"
            )

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(
        main()
    )