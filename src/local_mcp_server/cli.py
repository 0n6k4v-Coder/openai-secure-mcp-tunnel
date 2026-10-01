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
    list_workspace_grants,
)


EXIT_OK = 0
EXIT_ERROR = 2


def _workspace_name(
    grant: dict[str, object],
) -> str:
    host_path = grant.get(
        "host_path"
    )

    if isinstance(
        host_path,
        str,
    ) and host_path:
        return Path(host_path).name or host_path

    workspace_id = grant.get(
        "workspace_id"
    )

    if isinstance(
        workspace_id,
        str,
    ):
        return workspace_id

    return "unknown"


def _print_json(
    value: object,
) -> None:
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

    print(
        "  ".join(
            header.ljust(widths[index])
            for index, header in enumerate(headers)
        )
    )

    print(
        "  ".join(
            "-" * width
            for width in widths
        )
    )

    for row in rows:
        print(
            "  ".join(
                value.ljust(widths[index])
                for index, value in enumerate(row)
            )
        )


def _sandbox_status_value(
    sandbox: dict[str, object],
) -> str:
    status = sandbox.get(
        "status"
    )

    if status is not None and status != "":
        return str(status)

    phase = sandbox.get(
        "phase"
    )

    if phase is not None and phase != "":
        return str(phase)

    return "UNKNOWN"


def _sandbox_records() -> list[dict[str, object]]:
    data = json.loads(
        list_sandboxes()
    )

    if not isinstance(
        data,
        list,
    ):
        raise RuntimeError(
            "OpenShell returned an invalid sandbox list."
        )

    return [
        item
        for item in data
        if isinstance(item, dict)
    ]


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
            f"Host workspace name '{selector}' is ambiguous. "
            "Use the host workspace ID shown by "
            "'mcp-sandbox host-workspace list'."
        )

    raise ValueError(
        f"Host workspace '{selector}' was not found. "
        "Run 'mcp-sandbox host-workspace list'."
    )


def _run_workspace_broker(
    command: list[str],
) -> dict[str, object] | list[dict[str, object]]:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "local_mcp_server.workspace.broker",
                *command,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SandboxError(
            "The Python interpreter required to run the host workspace "
            "broker is not available."
        ) from exc

    if completed.returncode != 0:
        message = completed.stderr.strip()

        if not message:
            message = (
                "The host workspace broker failed "
                f"with exit code {completed.returncode}."
            )

        raise RuntimeError(
            message
        )

    try:
        result = json.loads(
            completed.stdout
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "The host workspace broker returned invalid JSON."
        ) from exc

    if not isinstance(
        result,
        (dict, list),
    ):
        raise RuntimeError(
            "The host workspace broker returned an invalid result."
        )

    return result


def _workspace_list(
    json_output: bool,
) -> int:
    grants = _workspace_records()

    if json_output:
        _print_json(grants)
        return EXIT_OK

    rows = [
        [
            _workspace_name(grant),
            str(
                grant.get(
                    "workspace_id",
                    "",
                )
            ),
            str(
                grant.get(
                    "host_path",
                    "",
                )
            ),
            "RO"
            if bool(
                grant.get(
                    "read_only",
                    False,
                )
            )
            else "RW",
        ]
        for grant in grants
    ]

    if not rows:
        print(
            "No authorized host workspaces."
        )
        return EXIT_OK

    _print_table(
        [
            "NAME",
            "HOST WORKSPACE ID",
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
    grant = _run_workspace_broker(
        [
            "authorize",
            host_path,
        ]
    )

    if not isinstance(
        grant,
        dict,
    ):
        raise RuntimeError(
            "The host workspace broker returned invalid authorization metadata."
        )

    if json_output:
        _print_json(grant)
        return EXIT_OK

    print(
        "Host workspace authorized."
    )
    print()
    print(
        f"Name:             {_workspace_name(grant)}"
    )
    print(
        f"Host workspace ID: {grant['workspace_id']}"
    )
    print(
        f"Host directory:    {grant['host_path']}"
    )
    print(
        f"Sandbox path:      {grant['target']}"
    )
    print(
        "Access:            "
        + (
            "read-only"
            if bool(
                grant.get(
                    "read_only",
                    False,
                )
            )
            else "read/write"
        )
    )

    return EXIT_OK


def _workspace_revoke(
    workspace_id: str,
    json_output: bool,
) -> int:
    result = _run_workspace_broker(
        [
            "revoke",
            workspace_id,
        ]
    )

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "The host workspace broker returned invalid revocation metadata."
        )

    if json_output:
        _print_json(result)
        return EXIT_OK

    print(
        f"Host workspace revoked: "
        f"{result['workspace_id']}"
    )

    volume_name = result.get(
        "volume_name"
    )

    if isinstance(
        volume_name,
        str,
    ) and volume_name:
        print(
            "Managed volume removal was requested by "
            "the host workspace broker: "
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

    rows = []

    for sandbox in records:
        host_workspace_id = sandbox.get(
            "host_workspace_id"
        )

        if not isinstance(
            host_workspace_id,
            str,
        ):
            host_workspace_id = ""

        rows.append(
            [
                str(
                    sandbox.get(
                        "name",
                        "",
                    )
                ),
                _sandbox_status_value(
                    sandbox
                ),
                host_workspace_id,
                str(
                    sandbox.get(
                        "id",
                        "",
                    )
                ),
            ]
        )

    if not rows:
        print(
            "No sandboxes found."
        )
        return EXIT_OK

    _print_table(
        [
            "NAME",
            "STATUS",
            "HOST WORKSPACE ID",
            "ID",
        ],
        rows,
    )

    print()
    print(
        f"{len(rows)} sandbox(es)."
    )

    return EXIT_OK


def _sandbox_inspect(
    name: str,
    json_output: bool,
) -> int:
    data = json.loads(
        sandbox_status(name)
    )

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "OpenShell returned invalid sandbox metadata."
        )

    if json_output:
        _print_json(data)
        return EXIT_OK

    print(
        "Sandbox"
    )
    print(
        "-------"
    )
    print(
        f"Name:      {data.get('name', name)}"
    )
    print(
        "OpenShell workspace: "
        f"{data.get('workspace', '')}"
    )
    print(
        "Status:    "
        f"{_sandbox_status_value(data)}"
    )
    print(
        f"ID:        {data.get('id', '')}"
    )

    host_workspace_id = data.get(
        "host_workspace_id"
    )

    if isinstance(
        host_workspace_id,
        str,
    ):
        print(
            "Host workspace ID: "
            f"{host_workspace_id}"
        )

    host_workspace = data.get(
        "host_workspace"
    )

    if isinstance(
        host_workspace,
        dict,
    ):
        print(
            "Host workspace authorized: "
            f"{host_workspace.get('authorized', False)}"
        )

        host_path = host_workspace.get(
            "host_path"
        )

        if isinstance(
            host_path,
            str,
        ):
            print(
                f"Host directory: {host_path}"
            )

    labels = data.get(
        "labels"
    )

    if labels:
        print(
            f"Labels:    {labels}"
        )

    return EXIT_OK


def _select_workspace_interactively(
    grants: list[dict[str, object]],
) -> dict[str, object]:
    if not sys.stdin.isatty():
        raise ValueError(
            "--host-workspace is required when stdin is not interactive."
        )

    print(
        "Select an authorized host workspace:"
    )
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
            f"Host workspace [1-{len(grants)}]: "
        ).strip()
    except EOFError as exc:
        raise ValueError(
            "Host workspace selection was cancelled."
        ) from exc

    try:
        selected = int(answer)
    except ValueError as exc:
        raise ValueError(
            "Host workspace selection must be a number."
        ) from exc

    if selected < 1 or selected > len(grants):
        raise ValueError(
            "Host workspace selection is out of range."
        )

    return grants[
        selected - 1
    ]


def _sandbox_create(
    name: str,
    workspace_selector: str | None,
    json_output: bool,
) -> int:
    grants = _workspace_records()

    if not grants:
        raise ValueError(
            "No authorized host workspaces exist. "
            "Run 'mcp-sandbox host-workspace add <directory>' first."
        )

    if workspace_selector:
        grant = _find_workspace(
            workspace_selector
        )
    else:
        grant = _select_workspace_interactively(
            grants
        )

    workspace_id = grant.get(
        "workspace_id"
    )

    if not isinstance(
        workspace_id,
        str,
    ) or not workspace_id:
        raise RuntimeError(
            "Selected host workspace has no workspace ID."
        )

    data = json.loads(
        create_sandbox(
            name=name,
            workspace_id=workspace_id,
        )
    )

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "OpenShell returned invalid sandbox metadata."
        )

    if json_output:
        _print_json(data)
        return EXIT_OK

    print(
        "Sandbox created."
    )
    print()
    print(
        f"Name:                {data.get('name', name)}"
    )
    print(
        "OpenShell workspace: "
        f"{data.get('workspace', 'default')}"
    )
    print(
        f"Host workspace ID:   {workspace_id}"
    )
    print(
        "Sandbox path:        /workspace/project"
    )
    print(
        "Status:              "
        f"{_sandbox_status_value(data)}"
    )

    return EXIT_OK


def _sandbox_delete(
    name: str,
    json_output: bool,
) -> int:
    result = json.loads(
        delete_sandbox(name)
    )

    if not isinstance(
        result,
        dict,
    ):
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
        help="List all OpenShell sandboxes.",
    )
    _add_json_argument(
        list_parser
    )
    list_parser.set_defaults(
        handler="sandbox_list"
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Show one OpenShell sandbox.",
    )
    _add_json_argument(
        inspect_parser
    )
    inspect_parser.add_argument(
        "name",
        help="Sandbox name.",
    )
    inspect_parser.set_defaults(
        handler="sandbox_inspect"
    )

    create_parser = subparsers.add_parser(
        "create",
        help=(
            "Create a sandbox using an authorized "
            "host workspace grant."
        ),
    )
    _add_json_argument(
        create_parser
    )
    create_parser.add_argument(
        "name",
        help="Sandbox name.",
    )
    create_parser.add_argument(
        "--host-workspace",
        dest="workspace",
        help=(
            "Host workspace name or host workspace ID. "
            "This is an authorization grant, not an "
            "OpenShell workspace."
        ),
    )
    create_parser.add_argument(
        "--workspace",
        dest="workspace",
        help=argparse.SUPPRESS,
    )
    create_parser.set_defaults(
        handler="sandbox_create"
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
        handler="sandbox_connect"
    )

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete an OpenShell sandbox.",
    )
    _add_json_argument(
        delete_parser
    )
    delete_parser.add_argument(
        "name",
        help="Sandbox name.",
    )
    delete_parser.set_defaults(
        handler="sandbox_delete"
    )

    host_workspace_parser = subparsers.add_parser(
        "host-workspace",
        help=(
            "Manage human-authorized host workspace grants."
        ),
    )

    host_workspace_subparsers = (
        host_workspace_parser.add_subparsers(
            dest="workspace_command",
            required=True,
        )
    )

    host_workspace_list_parser = (
        host_workspace_subparsers.add_parser(
            "list",
            help="List authorized host workspace grants.",
        )
    )
    _add_json_argument(
        host_workspace_list_parser
    )
    host_workspace_list_parser.set_defaults(
        handler="workspace_list"
    )

    host_workspace_add_parser = (
        host_workspace_subparsers.add_parser(
            "add",
            help="Authorize one host directory.",
        )
    )
    _add_json_argument(
        host_workspace_add_parser
    )
    host_workspace_add_parser.add_argument(
        "host_path",
        help="Host directory to authorize.",
    )
    host_workspace_add_parser.set_defaults(
        handler="workspace_add"
    )

    host_workspace_revoke_parser = (
        host_workspace_subparsers.add_parser(
            "revoke",
            help="Revoke one host workspace grant.",
        )
    )
    _add_json_argument(
        host_workspace_revoke_parser
    )
    host_workspace_revoke_parser.add_argument(
        "workspace_id",
        help="Host workspace grant ID beginning with ws_.",
    )
    host_workspace_revoke_parser.set_defaults(
        handler="workspace_revoke"
    )

    workspace_parser = subparsers.add_parser(
        "workspace",
        help=argparse.SUPPRESS,
    )

    workspace_subparsers = (
        workspace_parser.add_subparsers(
            dest="workspace_command",
            required=True,
        )
    )

    workspace_list_parser = (
        workspace_subparsers.add_parser(
            "list",
            help=argparse.SUPPRESS,
        )
    )
    _add_json_argument(
        workspace_list_parser
    )
    workspace_list_parser.set_defaults(
        handler="workspace_list"
    )

    workspace_add_parser = (
        workspace_subparsers.add_parser(
            "add",
            help=argparse.SUPPRESS,
        )
    )
    _add_json_argument(
        workspace_add_parser
    )
    workspace_add_parser.add_argument(
        "host_path",
        help=argparse.SUPPRESS,
    )
    workspace_add_parser.set_defaults(
        handler="workspace_add"
    )

    workspace_revoke_parser = (
        workspace_subparsers.add_parser(
            "revoke",
            help=argparse.SUPPRESS,
        )
    )
    _add_json_argument(
        workspace_revoke_parser
    )
    workspace_revoke_parser.add_argument(
        "workspace_id",
        help=argparse.SUPPRESS,
    )
    workspace_revoke_parser.set_defaults(
        handler="workspace_revoke"
    )

    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(
        argv
    )

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
    raise SystemExit(
        main()
    )