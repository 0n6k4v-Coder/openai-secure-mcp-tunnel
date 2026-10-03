from __future__ import annotations

import argparse
from builtins import input
import getpass
import sys
from collections.abc import Sequence

from ..config.service import ConfigError, configure_openai
from ..infrastructure.openshell.tls import (
    OpenShellTLSStatusError,
    TLSStatus,
    get_status as get_openshell_tls_status,
    repair as repair_openshell_tls,
    setup as setup_openshell_tls,
)
from . import lifecycle
from .main import main as local_mcp_server_main
from . import workspace_broker

EXIT_OK = 0
EXIT_ERROR = 2


def _prompt_choice(title: str, options: list[str]) -> int:
    print(title)
    print()

    for index, option in enumerate(options, start=1):
        print(f"{index}. {option}")

    print()

    value = input("Select [1]: ").strip()

    if not value:
        return 1

    try:
        choice = int(value)
    except ValueError as exc:
        raise ValueError("Selection must be a number.") from exc

    if not 1 <= choice <= len(options):
        raise ValueError("Selection is out of range.")

    return choice


def _configure_openai() -> int:
    print()
    print("MCP Client Configuration")
    print()

    tunnel_id = input("CONTROL_PLANE_TUNNEL_ID: ").strip()
    api_key = getpass.getpass("CONTROL_PLANE_API_KEY: ")

    configure_openai(
        tunnel_id,
        api_key,
    )

    print()
    print("MCP client configuration saved.")

    return EXIT_OK


def _config_mcp_client(
    *,
    allow_skip: bool = False,
) -> int:
    options = ["OpenAI"]

    if allow_skip:
        options.append("Skip for now")

    choice = _prompt_choice(
        "MCP Clients",
        options,
    )

    if choice == 1:
        return _configure_openai()

    if allow_skip and choice == 2:
        print()
        print("MCP client configuration skipped.")
        print("You can configure it later with:")
        print("  mcpctl config mcp-client")
        return EXIT_OK

    raise ValueError("Unsupported MCP client selection.")


def _config() -> int:
    if _prompt_choice(
        "Configuration",
        ["MCP Clients"],
    ) != 1:
        raise ValueError(
            "Unsupported configuration selection."
        )

    return _config_mcp_client()


def _print_tls_status(status: TLSStatus) -> None:
    print("OpenShell TLS")
    print()
    print(
        f"State: {'✓ READY' if status.complete else '✗ NOT READY'}"
    )
    print(f"Path: {status.root}")

    if status.missing:
        print()
        print("Missing:")

        for path in status.missing:
            print(
                f"  - {path.relative_to(status.root)}"
            )

    if status.insecure_paths:
        print()
        print("Permissions:")

        for path in status.insecure_paths:
            print(
                f"  - {path.relative_to(status.root)}"
            )


def _setup() -> int:
    lifecycle.prepare_runtime()

    tls_status = setup_openshell_tls()

    lifecycle.validate_compose()
    lifecycle.start_core_services()

    _config_mcp_client(
        allow_skip=True,
    )

    lifecycle.reconcile_tunnel_client()

    final_status = lifecycle.verify(
        tls_status,
    )

    lifecycle.print_status(final_status)

    return EXIT_OK


def _status() -> int:
    tls_status = get_openshell_tls_status()
    status = lifecycle.get_status(tls_status)

    lifecycle.print_status(status)

    return (
        EXIT_OK
        if status.ready
        else EXIT_ERROR
    )


def _repair() -> int:
    lifecycle.prepare_runtime()

    tls_status = repair_openshell_tls()

    lifecycle.validate_compose()
    lifecycle.start_core_services()
    lifecycle.reconcile_tunnel_client()

    final_status = lifecycle.verify(
        tls_status,
    )

    lifecycle.print_status(final_status)

    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcpctl",
        description="Control CLI for the local MCP application.",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    commands.add_parser(
        "setup",
        help="Initialize and start the local MCP application.",
    )

    commands.add_parser(
        "status",
        help="Check local MCP application lifecycle state.",
    )

    commands.add_parser(
        "repair",
        help="Repair OpenShell runtime state and restart core services.",
    )

    sandbox = commands.add_parser(
        "sandbox",
        help="Manage OpenShell sandboxes.",
    )

    sandbox_commands = sandbox.add_subparsers(
        dest="sandbox_command",
        required=True,
    )

    sandbox_create = sandbox_commands.add_parser(
        "create",
        help="Create a sandbox.",
    )

    sandbox_create.add_argument("name")

    sandbox_create.add_argument(
        "--workspace",
        required=True,
        dest="workspace_id",
    )

    sandbox_create.add_argument(
        "--profile",
        choices=["default", "browser"],
        default="default",
    )

    sandbox_create.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
    )

    sandbox_commands.add_parser(
        "list",
        help="List sandboxes.",
    )

    sandbox_status = sandbox_commands.add_parser(
        "status",
        help="Show one sandbox.",
    )

    sandbox_status.add_argument("name")

    sandbox_status.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
    )

    sandbox_shell = sandbox_commands.add_parser(
        "shell",
        help="Open an interactive shell in a sandbox.",
    )

    sandbox_shell.add_argument("name")

    sandbox_exec = sandbox_commands.add_parser(
        "exec",
        help="Execute a command in a sandbox.",
    )

    sandbox_exec.add_argument("name")

    sandbox_exec.add_argument(
        "exec_command",
        nargs=argparse.REMAINDER,
    )

    sandbox_logs = sandbox_commands.add_parser(
        "logs",
        help="Show sandbox activity logs.",
    )

    sandbox_logs.add_argument("name")

    sandbox_start = sandbox_commands.add_parser(
        "start",
        help="Start a stopped or retained failed sandbox.",
    )

    sandbox_start.add_argument("name")

    sandbox_stop = sandbox_commands.add_parser(
        "stop",
        help="Stop a sandbox while retaining its state.",
    )

    sandbox_stop.add_argument("name")

    sandbox_restart = sandbox_commands.add_parser(
        "restart",
        help="Restart a sandbox using OpenShell stop then start.",
    )

    sandbox_restart.add_argument("name")

    sandbox_repair = sandbox_commands.add_parser(
        "repair",
        help="Retry startup of a retained failed sandbox.",
    )

    sandbox_repair.add_argument("name")

    sandbox_delete = sandbox_commands.add_parser(
        "delete",
        help="Delete a sandbox.",
    )

    sandbox_delete.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
    )

    sandbox_recreate = sandbox_commands.add_parser(
        "recreate",
        help="Delete and recreate a sandbox with its existing workspace and profile.",
    )

    sandbox_recreate.add_argument(
        "--yes",
        action="store_true",
        dest="confirmed",
        help="Confirm destructive delete-and-recreate operation.",
    )

    credential = commands.add_parser(
        "credential",
        help="Manage OpenShell credential providers.",
    )

    credential_commands = credential.add_subparsers(
        dest="credential_command",
        required=True,
    )

    credential_create = credential_commands.add_parser(
        "create",
        help="Create a persistent credential provider.",
    )

    credential_create.add_argument("name")

    credential_create.add_argument(
        "--type",
        required=True,
        dest="provider_type",
    )

    credential_create.add_argument(
        "--key",
        required=True,
        dest="credential_key",
    )

    credential_create.add_argument(
        "--yes",
        action="store_true",
        dest="confirmed",
    )

    credential_commands.add_parser(
        "list",
        help="List credential providers without credential values.",
    )

    credential_get = credential_commands.add_parser(
        "get",
        help="Inspect one credential provider without secret values.",
    )

    credential_get.add_argument("name")

    credential_update = credential_commands.add_parser(
        "update",
        help="Replace the stored credential value.",
    )

    credential_update.add_argument("name")

    credential_update.add_argument(
        "--key",
        required=True,
        dest="credential_key",
    )

    credential_update.add_argument(
        "--yes",
        action="store_true",
        dest="confirmed",
    )

    credential_delete = credential_commands.add_parser(
        "delete",
        help="Delete a credential provider.",
    )

    credential_delete.add_argument("name")

    credential_delete.add_argument(
        "--yes",
        action="store_true",
        dest="confirmed",
    )

    for command, help_text in (
        ("grant", "Grant a credential to one sandbox."),
        ("revoke", "Revoke a credential from one sandbox."),
    ):
        grant_parser = credential_commands.add_parser(
            command,
            help=help_text,
        )

        grant_parser.add_argument("sandbox_name")
        grant_parser.add_argument("credential_name")

        grant_parser.add_argument(
            "--yes",
            action="store_true",
            dest="confirmed",
        )

    workspace = commands.add_parser(
        "workspace",
        help="Manage workspace grants.",
    )

    workspace_commands = workspace.add_subparsers(
        dest="workspace_command",
        required=True,
    )

    workspace_authorize = workspace_commands.add_parser(
        "authorize",
        help="Authorize a host workspace.",
    )

    workspace_authorize.add_argument("host_path")

    workspace_revoke = workspace_commands.add_parser(
        "revoke",
        help="Revoke a workspace grant.",
    )

    workspace_revoke.add_argument("workspace_id")

    workspace_list = workspace_commands.add_parser(
        "list",
        help="List workspace grants.",
    )

    workspace_list.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
    )

    config = commands.add_parser(
        "config",
        help="Configure application components.",
    )

    config_commands = config.add_subparsers(
        dest="config_command",
        required=True,
    )

    mcp_client = config_commands.add_parser(
        "mcp-client",
        help="Configure MCP clients.",
    )

    mcp_client_commands = mcp_client.add_subparsers(
        dest="mcp_client_command",
    )

    mcp_client_commands.add_parser(
        "openai",
        help="Configure the OpenAI MCP client.",
    )

    return parser


def _delegate_local_cli(
    command: str,
    arguments: Sequence[str],
) -> int:
    return local_mcp_server_main(
        [command, *arguments]
    )


def _sandbox_arguments(
    args: argparse.Namespace,
) -> list[str]:
    if args.sandbox_command == "create":
        arguments = [
            "create",
            args.name,
            "--workspace",
            args.workspace_id,
            "--profile",
            args.profile,
        ]

        if args.json_output:
            arguments.append("--json")

        return arguments

    if args.sandbox_command == "list":
        return ["list"]

    if args.sandbox_command in {"status", "delete"}:
        arguments = [
            args.sandbox_command,
            args.name,
        ]

        if args.json_output:
            arguments.append("--json")

        return arguments

    if args.sandbox_command in {
        "shell",
        "logs",
        "start",
        "stop",
        "restart",
        "repair",
    }:
        return [
            args.sandbox_command,
            args.name,
        ]

    if args.sandbox_command == "recreate":
        arguments = [
            "recreate",
            args.name,
        ]

        if args.confirmed:
            arguments.append("--yes")

        return arguments

    if args.sandbox_command == "exec":
        return [
            "exec",
            args.name,
            *args.exec_command,
        ]

    raise RuntimeError(
        f"Unsupported sandbox command: {args.sandbox_command}"
    )


def _credential_arguments(
    args: argparse.Namespace,
) -> list[str]:
    command = args.credential_command

    if command == "list":
        return ["list"]

    if command == "get":
        return [
            "get",
            args.name,
        ]

    if command == "create":
        arguments = [
            "create",
            args.name,
            "--type",
            args.provider_type,
            "--key",
            args.credential_key,
        ]

    elif command == "update":
        arguments = [
            "update",
            args.name,
            "--key",
            args.credential_key,
        ]

    elif command == "delete":
        arguments = [
            "delete",
            args.name,
        ]

    elif command in {"grant", "revoke"}:
        arguments = [
            command,
            args.sandbox_name,
            args.credential_name,
        ]

    else:
        raise RuntimeError(
            f"Unsupported credential command: {command}"
        )

    if args.confirmed:
        arguments.append("--yes")

    return arguments


def _workspace_arguments(
    args: argparse.Namespace,
) -> list[str]:
    command = args.workspace_command

    if command == "authorize":
        return [
            "authorize",
            args.host_path,
        ]

    if command == "revoke":
        return [
            "revoke",
            args.workspace_id,
        ]

    if command == "list":
        arguments = ["list"]

        if args.json_output:
            arguments.append("--json")

        return arguments

    raise RuntimeError(
        f"Unsupported workspace command: {command}"
    )


def main(
    argv: list[str] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "setup":
            return _setup()

        if args.command == "status":
            return _status()

        if args.command == "repair":
            return _repair()

        if args.command == "config":
            if args.config_command != "mcp-client":
                raise RuntimeError(
                    f"Unsupported config command: "
                    f"{args.config_command}"
                )

            if args.mcp_client_command is None:
                return _config_mcp_client()

            if args.mcp_client_command == "openai":
                return _configure_openai()

            raise RuntimeError(
                "Unsupported MCP client command: "
                f"{args.mcp_client_command}"
            )

        if args.command == "sandbox":
            return _delegate_local_cli(
                "sandbox",
                _sandbox_arguments(args),
            )

        if args.command == "credential":
            return _delegate_local_cli(
                "credential",
                _credential_arguments(args),
            )

        if args.command == "workspace":
            return workspace_broker.main(
                _workspace_arguments(args)
            )

        raise RuntimeError(
            f"Unsupported command: {args.command}"
        )

    except KeyboardInterrupt:
        print(
            "\nCancelled.",
            file=sys.stderr,
        )
        return 130

    except (
        ConfigError,
        lifecycle.LifecycleError,
        OpenShellTLSStatusError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())