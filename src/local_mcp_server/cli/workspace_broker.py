from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from ..workspace import repository as workspace_service
from ..workspace.domain import canonicalize_host_workspace


GRANTS_READ_ONLY = workspace_service.GRANTS_READ_ONLY

SANDBOX_UID = 10001
SANDBOX_GID = 10001
SANDBOX_TARGET = "/workspace/project"
ACL_HELPER_IMAGE = os.environ.get(
    "WORKSPACE_ACL_HELPER_IMAGE",
    "local-mcp-workspace-acl-helper:1.0.0",
)

PROTECTED_WORKSPACE_PATHS = (
    Path(".env"),
    Path(".secrets"),
    Path(".state"),
    Path("deploy/openshell/jwt"),
)

EXCLUDED_WORKSPACE_PATHS = (
    Path(".git"),
    Path(".venv"),
    Path(".ruff_cache"),
    Path(".pytest_cache"),
    Path(".mypy_cache"),
    Path(".pyright"),
    Path("deploy/docker/workspace-acl-helper"),
)

EXCLUDED_WORKSPACE_DIRECTORY_NAMES = {
    "__pycache__",
}

OWNER_ONLY_DIRECTORY_MODE = 0o700
OWNER_ONLY_FILE_MODE = 0o600


def _load_grants() -> dict[str, dict[str, object]]:
    grants_file = workspace_service.WORKSPACE_GRANTS_FILE

    if not grants_file.exists():
        return {}

    try:
        data = json.loads(
            grants_file.read_text(
                encoding="utf-8",
            )
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError("Workspace grants file contains invalid JSON.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Workspace grants file must contain a JSON object.")

    grants: dict[str, dict[str, object]] = {}

    for workspace_id, grant in data.items():
        if not isinstance(
            workspace_id,
            str,
        ):
            continue

        if not isinstance(
            grant,
            dict,
        ):
            continue

        grants[workspace_id] = grant

    return grants


def _save_grants(
    grants: dict[str, dict[str, object]],
) -> None:
    grants_file = workspace_service.WORKSPACE_GRANTS_FILE

    grants_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = grants_file.with_suffix(".tmp")

    temporary_path.write_text(
        json.dumps(
            grants,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        temporary_path,
        grants_file,
    )


def _workspace_id() -> str:
    return f"ws_{uuid.uuid4().hex}"


def _volume_name(
    workspace_id: str,
) -> str:
    return f"mcp-ws-{workspace_id.removeprefix('ws_')}"


def _run_command(
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required host command is unavailable: {command[0]}"
        ) from exc


def _host_user_id() -> int:
    return os.getuid()


def _host_group_id() -> int:
    return os.getgid()


def _require_docker() -> str:
    executable = shutil.which("docker")

    if executable is None:
        raise RuntimeError(
            "docker is required to manage workspace ACLs."
        )

    return executable


def _is_protected_path(
    path: Path,
    root: Path,
) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True

    for protected in PROTECTED_WORKSPACE_PATHS:
        if relative == protected or protected in relative.parents:
            return True

    return False


def _is_excluded_path(
    path: Path,
    root: Path,
) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True

    if any(
        part in EXCLUDED_WORKSPACE_DIRECTORY_NAMES
        for part in relative.parts
    ):
        return True

    for excluded in EXCLUDED_WORKSPACE_PATHS:
        if relative == excluded or excluded in relative.parents:
            return True

    return False


def _validate_protected_path_permissions(
    host_path: Path,
) -> None:
    for relative in PROTECTED_WORKSPACE_PATHS:
        protected_path = host_path / relative

        if not protected_path.exists():
            continue

        mode = protected_path.stat().st_mode

        if protected_path.is_dir():
            required_mode = OWNER_ONLY_DIRECTORY_MODE
        else:
            required_mode = OWNER_ONLY_FILE_MODE

        actual_mode = mode & 0o777

        if actual_mode != required_mode:
            raise RuntimeError(
                "Protected workspace path has unsafe permissions: "
                f"{protected_path} is {actual_mode:03o}; "
                f"expected {required_mode:03o}. "
                "Harden the protected path before authorizing "
                "the workspace for sandbox write access."
            )


def _run_acl_helper(
    host_path: Path,
    *,
    operation: str,
    host_uid: int | None = None,
    host_gid: int | None = None,
) -> None:
    docker = _require_docker()

    resolved_path = host_path.resolve()

    if host_uid is None:
        host_uid = _host_user_id()

    if host_gid is None:
        host_gid = _host_group_id()

    if host_uid < 1 or host_gid < 1:
        raise RuntimeError(
            "Workspace ACL helper requires a non-root host UID and GID."
        )

    if SANDBOX_UID < 1 or SANDBOX_GID < 1:
        raise RuntimeError(
            "Workspace ACL helper requires a non-root Sandbox UID and GID."
        )

    if operation not in {
        "provision-sandbox-acl",
        "remove-sandbox-acl",
    }:
        raise ValueError(f"Unsupported workspace ACL operation: {operation}")

    if not resolved_path.is_dir():
        raise RuntimeError(
            f"Workspace grant host path is not a directory: {resolved_path}"
        )

    completed = _run_command(
        [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "DAC_OVERRIDE",
            "--cap-add",
            "FOWNER",
            "--user",
            "0:0",
            "--mount",
            f"type=bind,source={resolved_path},target=/workspace",
            ACL_HELPER_IMAGE,
            operation,
            str(SANDBOX_UID),
            str(host_uid),
        ]
    )

    if completed.returncode != 0:
        message = completed.stderr.strip()

        if not message:
            message = (
                "Workspace ACL helper failed with "
                f"exit code {completed.returncode}."
            )

        raise RuntimeError(message)


def _provision_sandbox_acl(
    host_path: Path,
    *,
    host_uid: int | None = None,
    host_gid: int | None = None,
) -> None:
    """Provision broker-managed ACLs through the constrained root helper.

    Workspace files may already be owned by the Sandbox UID. Running setfacl
    directly as the host user therefore cannot reliably modify them. The
    helper receives only the canonical workspace path and has only the
    capabilities required to manage POSIX ACL metadata.
    """
    _validate_protected_path_permissions(host_path)

    _run_acl_helper(
        host_path,
        operation="provision-sandbox-acl",
        host_uid=host_uid,
        host_gid=host_gid,
    )


def _remove_sandbox_acl(
    host_path: Path,
    *,
    host_uid: int | None = None,
    host_gid: int | None = None,
) -> None:
    """Remove broker-managed ACLs through the constrained root helper."""
    _run_acl_helper(
        host_path,
        operation="remove-sandbox-acl",
        host_uid=host_uid,
        host_gid=host_gid,
    )


def _remove_sandbox_acl_with_helper(
    host_path: Path,
    *,
    host_uid: int | None = None,
    host_gid: int | None = None,
) -> None:
    """Backward-compatible wrapper for the helper-based ACL removal."""
    _remove_sandbox_acl(
        host_path,
        host_uid=host_uid,
        host_gid=host_gid,
    )


def _docker_volume_exists(
    volume_name: str,
) -> bool:
    docker = shutil.which("docker")

    if docker is None:
        return False

    completed = _run_command(
        [
            docker,
            "volume",
            "inspect",
            volume_name,
        ]
    )

    return completed.returncode == 0


def _create_host_backed_volume(
    volume_name: str,
    host_path: Path,
) -> None:
    docker = shutil.which("docker")

    if docker is None:
        raise RuntimeError(
            "docker is required to create the host-backed workspace volume."
        )

    if _docker_volume_exists(volume_name):
        return

    completed = _run_command(
        [
            docker,
            "volume",
            "create",
            "--driver",
            "local",
            "--opt",
            "type=none",
            "--opt",
            "o=bind",
            "--opt",
            f"device={host_path}",
            volume_name,
        ]
    )

    if completed.returncode != 0:
        message = completed.stderr.strip()

        if not message:
            message = (
                f"docker volume create failed with exit code {completed.returncode}."
            )

        raise RuntimeError(message)


def _remove_volume(
    volume_name: str,
) -> None:
    docker = shutil.which("docker")

    if docker is None:
        raise RuntimeError("docker is required to remove the workspace volume.")

    if not _docker_volume_exists(volume_name):
        return

    completed = _run_command(
        [
            docker,
            "volume",
            "rm",
            volume_name,
        ]
    )

    if completed.returncode != 0:
        message = completed.stderr.strip()

        if not message:
            message = f"docker volume rm failed with exit code {completed.returncode}."

        raise RuntimeError(message)


def create_workspace_grant(
    host_path: str,
    *,
    create_volume: bool = True,
) -> dict[str, object]:
    if GRANTS_READ_ONLY:
        raise RuntimeError(
            "Workspace grants are configured read-only; "
            "refusing to create a writable grant."
        )

    resolved_host_path = canonicalize_host_workspace(host_path)

    workspace_id = _workspace_id()
    volume_name = _volume_name(workspace_id)
    host_uid = _host_user_id()
    host_gid = _host_group_id()

    _provision_sandbox_acl(
        resolved_host_path,
        host_uid=host_uid,
        host_gid=host_gid,
    )

    try:
        if create_volume:
            _create_host_backed_volume(
                volume_name,
                resolved_host_path,
            )
    except Exception:
        _remove_sandbox_acl(
            resolved_host_path,
            host_uid=host_uid,
            host_gid=host_gid,
        )
        raise

    grants = _load_grants()

    grant = {
        "host_path": str(resolved_host_path),
        "host_gid": host_gid,
        "host_uid": host_uid,
        "read_only": False,
        "target": SANDBOX_TARGET,
        "volume_name": volume_name,
    }

    grants[workspace_id] = grant

    try:
        _save_grants(grants)
    except Exception:
        if create_volume:
            _remove_volume(volume_name)

        _remove_sandbox_acl(
            resolved_host_path,
            host_uid=host_uid,
            host_gid=host_gid,
        )

        raise

    return {
        "workspace_id": workspace_id,
        **grant,
    }


def revoke_workspace_grant(
    workspace_id: str,
    *,
    remove_volume: bool = True,
) -> dict[str, object]:
    if GRANTS_READ_ONLY:
        raise RuntimeError(
            "Workspace grants are configured read-only; "
            "refusing to revoke writable grants."
        )

    if not workspace_id:
        raise ValueError("workspace_id must not be empty.")

    if not workspace_id.startswith("ws_"):
        raise ValueError("workspace_id has an invalid format.")

    grants = _load_grants()

    grant = grants.get(workspace_id)

    if grant is None:
        raise ValueError(f"Workspace grant '{workspace_id}' was not found.")

    host_path_value = grant.get("host_path")

    if not isinstance(
        host_path_value,
        str,
    ):
        raise RuntimeError("Workspace grant has no valid host path.")

    host_path = Path(host_path_value).resolve()

    volume_name_value = grant.get("volume_name")

    if not isinstance(
        volume_name_value,
        str,
    ):
        raise RuntimeError("Workspace grant has no valid volume name.")

    host_uid_value = grant.get("host_uid")
    if host_uid_value is None:
        host_uid = _host_user_id()
    elif isinstance(host_uid_value, int) and not isinstance(host_uid_value, bool):
        host_uid = host_uid_value
    else:
        raise RuntimeError("Workspace grant has no valid host UID.")

    host_gid_value = grant.get("host_gid")
    if host_gid_value is None:
        host_gid = _host_group_id()
    elif isinstance(host_gid_value, int) and not isinstance(host_gid_value, bool):
        host_gid = host_gid_value
    else:
        raise RuntimeError("Workspace grant has no valid host GID.")

    _remove_sandbox_acl_with_helper(
        host_path,
        host_uid=host_uid,
        host_gid=host_gid,
    )

    if remove_volume:
        _remove_volume(volume_name_value)

    del grants[workspace_id]

    _save_grants(grants)

    return {
        "workspace_id": workspace_id,
        "host_path": str(host_path),
        "volume_name": volume_name_value,
        "revoked": True,
    }


def _authorize(
    host_path: str,
) -> dict[str, object]:
    return create_workspace_grant(host_path)


def _revoke(
    workspace_id: str,
) -> dict[str, object]:
    return revoke_workspace_grant(workspace_id)


def _list_grants() -> list[dict[str, object]]:
    grants = _load_grants()

    return [
        {
            "workspace_id": workspace_id,
            **grant,
        }
        for workspace_id, grant in sorted(grants.items())
    ]


def main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=("Trusted host-side workspace ACL and Docker-volume broker.")
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    authorize_parser = subparsers.add_parser("authorize")
    authorize_parser.add_argument("host_path")

    revoke_parser = subparsers.add_parser("revoke")
    revoke_parser.add_argument("workspace_id")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output workspace grants as JSON.",
    )

    args = parser.parse_args(argv)

    if args.command == "authorize":
        result = _authorize(args.host_path)
        print(
            json.dumps(
                result,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "revoke":
        result = _revoke(args.workspace_id)
        print(
            json.dumps(
                result,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "list":
        result = _list_grants()

        if args.json_output:
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
            )

        return 0

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())