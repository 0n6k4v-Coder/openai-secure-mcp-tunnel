from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .sandbox import (
    OPEN_SHELL_GATEWAY,
    SandboxError,
    create_sandbox,
    delete_sandbox,
    list_sandboxes,
    sandbox_status,
)
from .workspace import (
    create_workspace_grant,
    list_workspace_grants,
    revoke_workspace_grant,
)


EXIT_OK = 0
EXIT_ERROR = 2


def _workspace_name(grant: dict[str, object]) -> str:
    host_path = grant.get("host_path")

    if isinstance(host_path, str) and host_path:
        return Path(host_path).name or host_path

    workspace_id = grant.get("workspace_id")

    if isinstance(workspace_id, str):
        return workspace_id

    return "unknown"


def _print_json(value: object) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        )
    )


def _print_table(
    headers: list[str],
    rows: list[list[str]],
) -> None:
    if not rows:
        print("No results.")
        return

    widths = [
        len(header)
        for header in headers
    ]

    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(
                widths[index],
                len(value),
            )

    header_line = "  ".join(
        header.ljust(widths[index])
        for index, header in enumerate(headers)
    )

    separator = "  ".join(
        "-" * width
        for width in widths
    )

    print(header_line)
    print(separator)

    for row in rows:
        print(
            "  ".join(
                value.ljust(widths[index])
                for index, value in enumerate(row)
            )
        )


def _sandbox_records() -> list[dict[str, object]]:
    payload = list_sandboxes()
    data = json.loads(payload)

    if not isinstance(data, list):
        raise RuntimeError(
            "OpenShell returned an invalid sandbox list."
        )

    records: list[dict[str, object]] = []

    for item in data:
        if isinstance(item, dict):
            records.append(item)

    return records


def _workspace_records() -> list[dict[str, object]]:
    return list_workspace_grants()


def _find_workspace(
    selector: str,
) -> dict[str, object]:
    grants = _workspace_records()

    exact_id = [
        grant
        for grant in grants
        if grant.get("workspace_id") == selector
    ]

    if len(exact_id) == 1:
        return exact_id[0]

    name_matches = [
        grant
        for grant in grants
        if _workspace_name(grant) == selector
    ]

    if len(name_matches) == 1:
        return name_matches[0]

    if len(name_matches) > 1:
        raise ValueError(
            f"Workspace name '{selector}' is ambiguous. "
            "Use the workspace_id shown by "
            "'mcp-sandbox workspace list'."
        )

    raise ValueError(
        f"Workspace '{selector}' was not found. "
        "Run 'mcp-sandbox workspace list'."
    )


def _workspace_list(
    json_output: bool,
) -> int:
    grants = _workspace_records()

    if json_output:
        _print_json(grants)
        return EXIT_OK

    rows: list[list[str]] = []

    for grant in grants:
        rows.append(
            [
                _workspace_name(grant),
                str(grant.get("workspace_id", "")),
                str(grant.get("host_path", "")),
                "RO"
                if bool(grant.get("read_only", False))
                else "RW",
            ]
        )

    if not rows:
        print("No authorized workspaces.")
        return EXIT_OK

    _print_table(
        [
            "NAME",
            "WORKSPACE ID",
            "HOST DIRECTORY",
            "ACCESS",
        ],
        rows,
    )

    return EXIT_OK


def _workspace_add(
    host_path: str,
    json_output: bool,
) -> int:
    grant = create_workspace_grant(host_path)

    if json_output:
        _print_json(grant)
        return EXIT_OK

    print("Workspace authorized.")
    print()
    print(f"Name:           {_workspace_name(grant)}")
    print(f"Workspace ID:   {grant['workspace_id']}")
    print(f"Host directory: {grant['host_path']}")
    print(f"Sandbox path:   {grant['target']}")
    print(
        "Access:         "
        + (
            "read-only"
            if bool(grant.get("read_only", False))
            else "read/write"
        )
    )

    return EXIT_OK


def _workspace_revoke(
    workspace_id: str,
    json_output: bool,
) -> int:
    result = revoke_workspace_grant(
        workspace_id
    )

    if json_output:
        _print_json(result)
        return EXIT_OK

    print(
        f"Workspace revoked: {result['workspace_id']}"
    )

    volume_name = result.get("volume_name")

    if isinstance(volume_name, str) and volume_name:
        print(
            "Volume removal was requested by the workspace broker: "
            f"{volume_name}"
        )

    return EXIT_OK


def _sandbox_list(
    json_output: bool,
) -> int:
    records = _sandbox_records()

    if json_output:
        _print_json(records)
        return EXIT_OK

    rows: list[list[str]] = []

    for sandbox in records:
        status = sandbox.get("status")

        if not isinstance(status, str) or not status:
            status = sandbox.get("phase")

        if not isinstance(status, str) or not status:
            status = "UNKNOWN"

        rows.append(
            [
                str(sandbox.get("name", "")),
                status,
                str(sandbox.get("id", "")),
            ]
        )

    if not rows:
        print("No sandboxes found.")
        return EXIT_OK

    _print_table(
        [
            "NAME",
            "STATUS",
            "ID",
        ],
        rows,
    )

    print()
    print(f"{len(rows)} sandbox(es).")

    return EXIT_OK


def _sandbox_inspect(
    name: str,
    json_output: bool,
) -> int:
    payload = sandbox_status(name)
    data = json.loads(payload)

    if not isinstance(data, dict):
        raise RuntimeError(
            "OpenShell returned invalid sandbox metadata."
        )

    if json_output:
        _print_json(data)
        return EXIT_OK

    print("Sandbox")
    print("-------")
    print(f"Name:      {data.get('name', name)}")
    print(
        "Status:    "
        f"{data.get('status', data.get('phase', 'UNKNOWN'))}"
    )
    print(f"ID:        {data.get('id', '')}")

    labels = data.get("labels")

    if labels:
        print(f"Labels:    {labels}")

    return EXIT_OK


def _select_workspace_interactively(
    grants: list[dict[str, object]],
) -> dict[str, object]:
    if not sys.stdin.isatty():
        raise ValueError(
            "--workspace is required when stdin is not interactive."
        )

    print("Select a workspace:")
    print()

    for index, grant in enumerate(
        grants,
        start=1,
    ):
        print(
            f"{index}. "
            f"{_workspace_name(grant)} "
            f"({grant.get('host_path', '')})"
        )

    print()

    try:
        answer = input(
            f"Workspace [1-{len(grants)}]: "
        ).strip()
    except EOFError as exc:
        raise ValueError(
            "Workspace selection was cancelled."
        ) from exc

    try:
        selected = int(answer)
    except ValueError as exc:
        raise ValueError(
            "Workspace selection must be a number."
        ) from exc

    if selected < 1 or selected > len(grants):
        raise ValueError(
            "Workspace selection is out of range."
        )

    return grants[selected - 1]


def _sandbox_create(
    name: str,
    workspace_selector: str | None,
    json_output: bool,
) -> int:
    grants = _workspace_records()

    if not grants:
        raise ValueError(
            "No authorized workspaces exist. "
            "Run 'mcp-sandbox workspace add <directory>' first."
        )

    if workspace_selector:
        grant = _find_workspace(
            workspace_selector
        )
    else:
        grant = _select_workspace_interactively(
            grants
        )

    workspace_id = grant.get("workspace_id")

    if not isinstance(workspace_id, str) or not workspace_id:
        raise RuntimeError(
            "Selected workspace has no workspace_id."
        )

    payload = create_sandbox(
        name=name,
        workspace_id=workspace_id,
    )

    data = json.loads(payload)

    if not isinstance(data, dict):
        raise RuntimeError(
            "OpenShell returned invalid sandbox metadata."
        )

    if json_output:
        _print_json(data)
        return EXIT_OK

    print("Sandbox created.")
    print()
    print(f"Name:           {data.get('name', name)}")
    print(f"Workspace:      {_workspace_name(grant)}")
    print(f"Workspace ID:   {workspace_id}")
    print("Sandbox path:   /workspace/project")
    print(
        "Status:         "
        f"{data.get('status', data.get('phase', 'UNKNOWN'))}"
    )

    return EXIT_OK


def _sandbox_delete(
    name: str,
    json_output: bool,
) -> int:
    result = json.loads(
        delete_sandbox(name)
    )

    if not isinstance(result, dict):
        raise RuntimeError(
            "OpenShell returned invalid deletion metadata."
        )

    if json_output:
        _print_json(result)
        return EXIT_OK

    print(
        f"Sandbox deleted: {result['name']}"
    )

    return EXIT_OK


def _sandbox_connect(
    name: str,
) -> int:
    command = [
        "openshell",
    ]

    if OPEN_SHELL_GATEWAY:
        command.extend(
            [
                "--gateway-endpoint",
                OPEN_SHELL_GATEWAY,
            ]
        )

    command.extend(
        [
            "sandbox",
            "connect",
            name,
        ]
    )

    try:
        completed = subprocess.run(
            command,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SandboxError(
            "The OpenShell CLI is not installed or is not available "
            "on PATH. Install the OpenShell CLI before using "
            "'mcp-sandbox connect'."
        ) from exc

    return completed.returncode


def _add_json_argument(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print machine-readable JSON where supported.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-sandbox",
        description=(
            "Local control plane for OpenShell sandboxes "
            "and human-authorized host workspaces."
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Print machine-readable JSON where supported.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    list_parser = subparsers.add_parser(
        "list",
        help="List all sandboxes.",
    )
    _add_json_argument(list_parser)
    list_parser.set_defaults(
        handler="sandbox_list",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Show one sandbox.",
    )
    _add_json_argument(inspect_parser)
    inspect_parser.add_argument(
        "name",
        help="Sandbox name.",
    )
    inspect_parser.set_defaults(
        handler="sandbox_inspect",
    )

    create_parser = subparsers.add_parser(
        "create",
        help="Create a sandbox using an authorized workspace.",
    )
    _add_json_argument(create_parser)
    create_parser.add_argument(
        "name",
        help="Sandbox name.",
    )
    create_parser.add_argument(
        "--workspace",
        help=(
            "Workspace name or workspace_id. "
            "If omitted, choose interactively."
        ),
    )
    create_parser.set_defaults(
        handler="sandbox_create",
    )

    connect_parser = subparsers.add_parser(
        "connect",
        help="Open an interactive session in a sandbox.",
    )
    connect_parser.add_argument(
        "name",
        help="Sandbox name.",
    )
    connect_parser.set_defaults(
        handler="sandbox_connect",
    )

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a sandbox.",
    )
    _add_json_argument(delete_parser)
    delete_parser.add_argument(
        "name",
        help="Sandbox name.",
    )
    delete_parser.set_defaults(
        handler="sandbox_delete",
    )

    workspace_parser = subparsers.add_parser(
        "workspace",
        help="Manage human-authorized host workspaces.",
    )

    workspace_subparsers = workspace_parser.add_subparsers(
        dest="workspace_command",
        required=True,
    )

    workspace_list_parser = workspace_subparsers.add_parser(
        "list",
        help="List authorized workspaces.",
    )
    _add_json_argument(workspace_list_parser)
    workspace_list_parser.set_defaults(
        handler="workspace_list",
    )

    workspace_add_parser = workspace_subparsers.add_parser(
        "add",
        help="Authorize one host directory.",
    )
    _add_json_argument(workspace_add_parser)
    workspace_add_parser.add_argument(
        "host_path",
        help="Host directory to authorize.",
    )
    workspace_add_parser.set_defaults(
        handler="workspace_add",
    )

    workspace_revoke_parser = workspace_subparsers.add_parser(
        "revoke",
        help="Revoke one workspace capability.",
    )
    _add_json_argument(workspace_revoke_parser)
    workspace_revoke_parser.add_argument(
        "workspace_id",
        help="Workspace ID beginning with ws_.",
    )
    workspace_revoke_parser.set_defaults(
        handler="workspace_revoke",
    )

    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.handler == "workspace_list":
            return _workspace_list(
                args.json
            )

        if args.handler == "workspace_add":
            return _workspace_add(
                args.host_path,
                args.json,
            )

        if args.handler == "workspace_revoke":
            return _workspace_revoke(
                args.workspace_id,
                args.json,
            )

        if args.handler == "sandbox_list":
            return _sandbox_list(
                args.json
            )

        if args.handler == "sandbox_inspect":
            return _sandbox_inspect(
                args.name,
                args.json
            )

        if args.handler == "sandbox_create":
            return _sandbox_create(
                args.name,
                args.workspace,
                args.json,
            )

        if args.handler == "sandbox_delete":
            return _sandbox_delete(
                args.name,
                args.json,
            )

        if args.handler == "sandbox_connect":
            if args.json:
                raise ValueError(
                    "--json is not supported with 'connect'."
                )

            return _sandbox_connect(
                args.name
            )

        parser.error(
            f"unsupported command: {args.handler}"
        )

    except (
        ValueError,
        RuntimeError,
        SandboxError,
        json.JSONDecodeError,
    ) as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())