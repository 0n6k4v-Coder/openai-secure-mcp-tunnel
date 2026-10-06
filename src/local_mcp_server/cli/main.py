from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def _find_project_root() -> Path:
    candidates = [
        Path.cwd(),
        Path(__file__).resolve().parents[2],
    ]

    seen: set[Path] = set()

    for candidate in candidates:
        for root in (candidate, *candidate.parents):
            if root in seen:
                continue

            seen.add(root)

            compose_file = root / "deploy" / "compose.yaml"

            if compose_file.is_file():
                return root

    raise RuntimeError("Could not locate project root containing deploy/compose.yaml.")


PROJECT_ROOT = _find_project_root()
COMPOSE_FILE = PROJECT_ROOT / "deploy" / "compose.yaml"
ENV_FILE = PROJECT_ROOT / ".env"


from ..credentials.service import (  # noqa: E402
    CredentialError,
    create_credential,
    delete_credential,
    grant_credential,
    list_credentials,
    revoke_credential,
    show_credential,
    update_credential,
)

from ..sandbox.service import (  # noqa: E402
    SandboxError,
    create_sandbox,
    delete_sandbox,
    list_sandboxes,
    recreate_sandbox,
    sandbox_status,
    validate_command,
    validate_name,
)


EXIT_OK = 0
EXIT_ERROR = 2


def _command_exists(command: str) -> None:
    if shutil.which(command) is None:
        raise RuntimeError(
            f"Required command '{command}' is not installed or is not on PATH."
        )


def _require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"{description} not found: {path}")


def _compose_command(*args: str) -> list[str]:
    from ..runtime.context import get_runtime_context
    context = get_runtime_context()
    _require_file(COMPOSE_FILE, "Compose file")
    command = ["docker", "compose", "--file", str(COMPOSE_FILE)]
    if not context.is_default:
        command.extend(["--project-name", context.profile.compose_project_name])
    runtime_env_file = context.config_root / ".env"
    selected_env_file = runtime_env_file if not context.is_default and runtime_env_file.is_file() else ENV_FILE
    if selected_env_file.is_file():
        command.extend(["--env-file", str(selected_env_file)])

    command.extend(args)
    return command


def _run_passthrough(
    command: Sequence[str],
    *,
    cwd: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
) -> int:
    from ..runtime.context import get_runtime_context
    context = get_runtime_context()
    child_env = env if env is not None or context.is_default else context.child_environment()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=child_env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required command '{command[0]}' is not installed or is not on PATH."
        ) from exc

    return completed.returncode


def _run_capture(
    command: Sequence[str],
    *,
    cwd: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    from ..runtime.context import get_runtime_context
    context = get_runtime_context()
    child_env = env if env is not None or context.is_default else context.child_environment()
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            env=child_env,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required command '{command[0]}' is not installed or is not on PATH."
        ) from exc


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _parse_json(value: str) -> dict[str, object] | list[object]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenShell returned invalid JSON.") from exc

    if not isinstance(data, (dict, list)):
        raise RuntimeError("OpenShell returned an unexpected JSON value.")

    return data


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print("No results.")
        return

    widths = [len(header) for header in headers]

    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    print(
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    )

    print("  ".join("-" * width for width in widths))

    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _status_value(record: dict[str, object]) -> str:
    status = record.get("status")

    if status not in (None, ""):
        return str(status)

    phase = record.get("phase")

    if phase not in (None, ""):
        return str(phase)

    return "UNKNOWN"


def _start() -> int:
    _command_exists("docker")
    from . import lifecycle

    print("Starting local MCP application")
    print("Preflight: custom images")
    lifecycle.ensure_local_images()
    result = _run_passthrough(
        _compose_command(
            "up",
            "--build",
            "--remove-orphans",
            "--detach",
        )
    )
    if result == EXIT_OK:
        print("RESULT: START REQUEST COMPLETED")
        print("Next: mcpctl status")
    else:
        print(f"RESULT: START FAILED (exit code {result})", file=sys.stderr)
    return result


def _stop() -> int:
    _command_exists("docker")
    print("Stopping local MCP application")
    result = _run_passthrough(_compose_command("down"))
    if result == EXIT_OK:
        print("RESULT: STOPPED")
        print("Preserved: custom images, Docker volumes, workspace data, credentials, and configuration.")
    else:
        print(f"RESULT: STOP FAILED (exit code {result})", file=sys.stderr)
    return result


def _restart() -> int:
    _command_exists("docker")
    from . import lifecycle

    print("Restarting local MCP application")
    print("Preflight: custom images")
    lifecycle.ensure_local_images()
    result = _run_passthrough(
        _compose_command(
            "up",
            "--build",
            "--force-recreate",
            "--remove-orphans",
            "--detach",
        )
    )
    if result == EXIT_OK:
        print("RESULT: RESTART REQUEST COMPLETED")
        print("Next: mcpctl status")
    else:
        print(f"RESULT: RESTART FAILED (exit code {result})", file=sys.stderr)
    return result



def _status(json_output: bool) -> int:
    _command_exists("docker")

    compose = _run_capture(
        _compose_command(
            "ps",
            "--all",
            "--format",
            "json",
        )
    )

    if json_output:
        services: list[object] = []

        for line in compose.stdout.splitlines():
            if line.strip():
                try:
                    services.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Docker Compose returned invalid JSON status output."
                    ) from exc

        _print_json(
            {
                "project_root": str(PROJECT_ROOT),
                "services": services,
            }
        )
    else:
        print("Docker Compose")
        print("--------------")

        if compose.stdout.strip():
            print(compose.stdout.rstrip())
        elif compose.stderr.strip():
            print(compose.stderr.rstrip(), file=sys.stderr)
        else:
            print("No Compose containers found.")

    return compose.returncode


def _logs(
    service: str | None,
    follow: bool,
    tail: str,
) -> int:
    _command_exists("docker")

    command = _compose_command(
        "logs",
        "--tail",
        tail,
    )

    if follow:
        command.append("--follow")

    if service:
        command.append(service)

    return _run_passthrough(command)


def _sandbox_list(json_output: bool) -> int:
    data = _parse_json(list_sandboxes())

    if json_output:
        _print_json(data)
        return EXIT_OK

    if not isinstance(data, list):
        raise RuntimeError("OpenShell returned an invalid sandbox list.")

    rows: list[list[str]] = []

    for sandbox in data:
        if not isinstance(sandbox, dict):
            continue

        rows.append(
            [
                str(sandbox.get("name", "")),
                _status_value(sandbox),
                str(sandbox.get("profile", "default")),
                str(sandbox.get("host_workspace_id", "")),
                str(sandbox.get("id", "")),
            ]
        )

    _print_table(
        ["NAME", "STATUS", "PROFILE", "HOST WORKSPACE ID", "ID"],
        rows,
    )

    return EXIT_OK


def _sandbox_status(name: str, json_output: bool) -> int:
    data = _parse_json(sandbox_status(name))

    if not isinstance(data, dict):
        raise RuntimeError("OpenShell returned invalid sandbox metadata.")

    if json_output:
        _print_json(data)
        return EXIT_OK

    print(f"Name:                {data.get('name', name)}")
    print(f"Status:              {_status_value(data)}")
    print(f"Profile:             {data.get('profile', 'default')}")
    print(f"OpenShell workspace: {data.get('workspace', '')}")
    print(f"ID:                  {data.get('id', '')}")

    browser = data.get("browser")
    if isinstance(browser, dict):
        devtools = browser.get("devtools")
        if isinstance(devtools, dict):
            print(f"Chrome DevTools:     {devtools.get('state', 'unknown')}")

    host_workspace_id = data.get("host_workspace_id")
    if host_workspace_id:
        print(f"Host workspace ID:   {host_workspace_id}")

    return EXIT_OK


def _sandbox_create(
    name: str,
    workspace_id: str | None,
    standalone: bool,
    json_output: bool,
    profile: str = "default",
) -> int:
    if standalone and workspace_id is not None:
        raise ValueError("sandbox create cannot use --workspace with --standalone.")

    if not standalone and workspace_id is None:
        raise ValueError(
            "sandbox create requires either --workspace WORKSPACE_ID or --standalone."
        )

    if profile == "default":
        created = create_sandbox(
            name=name,
            workspace_id=workspace_id,
        )
    else:
        created = create_sandbox(
            name=name,
            workspace_id=workspace_id,
            profile=profile,
        )

    data = _parse_json(created)

    if not isinstance(data, dict):
        raise RuntimeError("OpenShell returned invalid sandbox metadata.")

    if json_output:
        _print_json(data)
        return EXIT_OK

    print("Sandbox created.")
    print(f"Name:                {data.get('name', name)}")
    print(f"Status:              {_status_value(data)}")
    print(f"Profile:             {data.get('profile', profile)}")

    if standalone:
        print("Application workspace: sandbox-local")
    else:
        print(f"Host workspace ID:   {workspace_id}")

    print("Sandbox path:        /workspace/project")

    return EXIT_OK


def _sandbox_delete(name: str, json_output: bool) -> int:
    data = _parse_json(delete_sandbox(name))

    if not isinstance(data, dict):
        raise RuntimeError("OpenShell returned invalid deletion metadata.")

    if json_output:
        _print_json(data)
        return EXIT_OK

    print(f"Sandbox deleted: {data.get('name', name)}")
    return EXIT_OK


def _sandbox_shell(name: str) -> int:
    validate_name(name)

    return _run_passthrough(
        _openshell_command(
            "sandbox",
            "exec",
            "--name",
            name,
            "--tty",
            "--",
            "/bin/bash",
            "-l",
        )
    )


def _sandbox_exec(name: str, command: list[str]) -> int:
    validate_name(name)

    if command and command[0] == "--":
        command = command[1:]

    if not command:
        raise ValueError("sandbox exec requires a command after '--'.")

    validate_command(" ".join(command))

    return _run_passthrough(
        _openshell_command(
            "sandbox",
            "exec",
            "--name",
            name,
            "--",
            *command,
        )
    )


def _sandbox_logs(name: str) -> int:
    validate_name(name)
    return _run_passthrough(_openshell_command("logs", name))


def _sandbox_start(name: str) -> int:
    validate_name(name)
    return _run_passthrough(_openshell_command("sandbox", "start", name))


def _sandbox_stop(name: str) -> int:
    validate_name(name)
    return _run_passthrough(_openshell_command("sandbox", "stop", name))


def _sandbox_restart(name: str) -> int:
    validate_name(name)

    stop_result = _sandbox_stop(name)

    if stop_result != EXIT_OK:
        return stop_result

    return _sandbox_start(name)


def _sandbox_repair(name: str) -> int:
    validate_name(name)

    return _sandbox_start(name)


def _sandbox_recreate(
    name: str,
    confirmed: bool,
) -> int:
    if not confirmed:
        raise ValueError("sandbox recreate requires --yes.")

    data = _parse_json(
        recreate_sandbox(name),
    )

    if not isinstance(data, dict):
        raise RuntimeError("OpenShell returned invalid sandbox metadata.")

    print("Sandbox recreated.")
    print(f"Name:                {data.get('name', name)}")
    print(f"Status:              {_status_value(data)}")
    print(f"Profile:             {data.get('profile', 'default')}")

    host_workspace_id = data.get("host_workspace_id")

    if host_workspace_id:
        print(f"Host workspace ID:   {host_workspace_id}")

    print("Sandbox path:        /workspace/project")

    return EXIT_OK


def _openshell_command(*args: str) -> list[str]:
    _command_exists("openshell")
    return ["openshell", *args]


def _credential_create(
    name: str,
    provider_type: str,
    credential_key: str,
    confirmed: bool,
) -> int:
    if not confirmed:
        raise ValueError("credential create requires --yes.")

    return create_credential(name, provider_type, credential_key)


def _credential_update(
    name: str,
    credential_key: str,
    confirmed: bool,
) -> int:
    if not confirmed:
        raise ValueError("credential update requires --yes.")

    return update_credential(name, credential_key)


def _credential_delete(name: str, confirmed: bool) -> int:
    if not confirmed:
        raise ValueError("credential delete requires --yes.")

    return delete_credential(name)


def _credential_grant(
    sandbox_name: str,
    credential_name: str,
    confirmed: bool,
) -> int:
    if not confirmed:
        raise ValueError("credential grant requires --yes.")

    return grant_credential(sandbox_name, credential_name)


def _credential_revoke(
    sandbox_name: str,
    credential_name: str,
    confirmed: bool,
) -> int:
    if not confirmed:
        raise ValueError("credential revoke requires --yes.")

    return revoke_credential(sandbox_name, credential_name)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcpctl",
        description="Local control CLI for the OpenAI Secure MCP Tunnel.",
    )

    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", help="Build and start the Compose stack.")
    start.set_defaults(handler=_start)

    stop = commands.add_parser("stop", help="Stop and remove the Compose stack.")
    stop.set_defaults(handler=_stop)

    restart = commands.add_parser(
        "restart",
        help="Rebuild and recreate the Compose stack.",
    )
    restart.set_defaults(handler=_restart)

    status = commands.add_parser("status", help="Show Compose service status.")
    status.add_argument("--json", dest="json_output", action="store_true")
    status.set_defaults(handler=_status)

    logs = commands.add_parser("logs", help="Show Compose service logs.")
    logs.add_argument(
        "service",
        nargs="?",
        choices=["openshell-gateway", "mcp-server", "tunnel-client"],
    )
    logs.add_argument("--follow", "-f", action="store_true")
    logs.add_argument("--tail", "-n", default="100")
    logs.set_defaults(handler=_logs)

    sandbox = commands.add_parser("sandbox", help="Manage OpenShell sandboxes.")
    sandbox_commands = sandbox.add_subparsers(
        dest="sandbox_command",
        required=True,
    )

    create = sandbox_commands.add_parser(
        "create",
        help="Create a host-backed or standalone sandbox.",
    )
    create.add_argument("name")

    workspace_source = create.add_mutually_exclusive_group(required=True)
    workspace_source.add_argument(
        "--workspace",
        dest="workspace_id",
        help="Use an authorized host workspace.",
    )
    workspace_source.add_argument(
        "--standalone",
        action="store_true",
        help="Create without a host workspace; use sandbox-local storage.",
    )

    create.add_argument(
        "--profile",
        choices=["default", "browser"],
        default="default",
    )
    create.add_argument("--json", dest="json_output", action="store_true")
    create.set_defaults(handler=_sandbox_create)

    list_parser = sandbox_commands.add_parser("list", help="List sandboxes.")
    list_parser.add_argument("--json", dest="json_output", action="store_true")
    list_parser.set_defaults(handler=_sandbox_list)

    status_parser = sandbox_commands.add_parser("status", help="Show one sandbox.")
    status_parser.add_argument("name")
    status_parser.add_argument("--json", dest="json_output", action="store_true")
    status_parser.set_defaults(handler=_sandbox_status)

    shell = sandbox_commands.add_parser(
        "shell",
        help="Open an interactive shell in a sandbox.",
    )
    shell.add_argument("name")
    shell.set_defaults(handler=_sandbox_shell)

    exec_parser = sandbox_commands.add_parser(
        "exec",
        help="Execute a command in a sandbox.",
    )
    exec_parser.add_argument("name")
    exec_parser.add_argument("exec_command", nargs=argparse.REMAINDER)
    exec_parser.set_defaults(handler=_sandbox_exec)

    logs_parser = sandbox_commands.add_parser(
        "logs",
        help="Show sandbox activity logs.",
    )
    logs_parser.add_argument("name")
    logs_parser.set_defaults(handler=_sandbox_logs)

    start_parser = sandbox_commands.add_parser(
        "start",
        help="Start a stopped or retained failed sandbox.",
    )
    start_parser.add_argument("name")
    start_parser.set_defaults(handler=_sandbox_start)

    stop_parser = sandbox_commands.add_parser(
        "stop",
        help="Stop a sandbox while retaining its state.",
    )
    stop_parser.add_argument("name")
    stop_parser.set_defaults(handler=_sandbox_stop)

    restart_parser = sandbox_commands.add_parser(
        "restart",
        help="Restart a sandbox using OpenShell stop then start.",
    )
    restart_parser.add_argument("name")
    restart_parser.set_defaults(handler=_sandbox_restart)

    repair_parser = sandbox_commands.add_parser(
        "repair",
        help="Retry startup of a retained failed sandbox.",
    )
    repair_parser.add_argument("name")
    repair_parser.set_defaults(handler=_sandbox_repair)

    delete = sandbox_commands.add_parser("delete", help="Delete a sandbox.")
    delete.add_argument("name")
    delete.add_argument("--json", dest="json_output", action="store_true")
    delete.set_defaults(handler=_sandbox_delete)

    recreate = sandbox_commands.add_parser(
        "recreate",
        help="Delete and recreate a sandbox with its existing workspace and profile.",
    )
    recreate.add_argument("name")
    recreate.add_argument(
        "--yes",
        action="store_true",
        dest="confirmed",
        help="Confirm destructive delete-and-recreate operation.",
    )
    recreate.set_defaults(handler=_sandbox_recreate)

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
    credential_create.add_argument("--type", required=True, dest="provider_type")
    credential_create.add_argument("--key", required=True, dest="credential_key")
    credential_create.add_argument("--yes", action="store_true", dest="confirmed")
    credential_create.set_defaults(handler=_credential_create)

    credential_list = credential_commands.add_parser(
        "list",
        help="List credential providers without credential values.",
    )
    credential_list.set_defaults(handler=lambda: list_credentials())

    credential_get = credential_commands.add_parser(
        "get",
        help="Inspect one credential provider without secret values.",
    )
    credential_get.add_argument("name")
    credential_get.set_defaults(handler=lambda name: show_credential(name))

    credential_update = credential_commands.add_parser(
        "update",
        help="Replace the stored credential value.",
    )
    credential_update.add_argument("name")
    credential_update.add_argument("--key", required=True, dest="credential_key")
    credential_update.add_argument("--yes", action="store_true", dest="confirmed")
    credential_update.set_defaults(handler=_credential_update)

    credential_delete = credential_commands.add_parser(
        "delete",
        help="Delete a credential provider.",
    )
    credential_delete.add_argument("name")
    credential_delete.add_argument("--yes", action="store_true", dest="confirmed")
    credential_delete.set_defaults(handler=_credential_delete)

    credential_grant = credential_commands.add_parser(
        "grant",
        help="Grant a credential to one sandbox.",
    )
    credential_grant.add_argument("sandbox_name")
    credential_grant.add_argument("credential_name")
    credential_grant.add_argument("--yes", action="store_true", dest="confirmed")
    credential_grant.set_defaults(handler=_credential_grant)

    credential_revoke = credential_commands.add_parser(
        "revoke",
        help="Revoke a credential from one sandbox.",
    )
    credential_revoke.add_argument("sandbox_name")
    credential_revoke.add_argument("credential_name")
    credential_revoke.add_argument("--yes", action="store_true", dest="confirmed")
    credential_revoke.set_defaults(handler=_credential_revoke)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "sandbox" and args.sandbox_command == "exec":
            return args.handler(args.name, list(args.exec_command))

        if args.command == "logs":
            return args.handler(args.service, args.follow, args.tail)

        if args.command == "status":
            return args.handler(args.json_output)

        if args.command == "sandbox" and args.sandbox_command == "create":
            if args.profile == "default":
                return args.handler(
                    args.name,
                    args.workspace_id,
                    args.standalone,
                    args.json_output,
                )

            return args.handler(
                args.name,
                args.workspace_id,
                args.standalone,
                args.json_output,
                args.profile,
            )

        if args.command == "sandbox" and args.sandbox_command == "list":
            return args.handler(args.json_output)

        if args.command == "sandbox" and args.sandbox_command in {
            "status",
            "delete",
        }:
            return args.handler(args.name, args.json_output)

        if args.command == "sandbox" and args.sandbox_command == "recreate":
            return args.handler(args.name, args.confirmed)

        if args.command == "sandbox":
            return args.handler(args.name)

        if args.command == "credential" and args.credential_command == "create":
            return args.handler(
                args.name,
                args.provider_type,
                args.credential_key,
                args.confirmed,
            )

        if args.command == "credential" and args.credential_command == "update":
            return args.handler(args.name, args.credential_key, args.confirmed)

        if args.command == "credential" and args.credential_command == "delete":
            return args.handler(args.name, args.confirmed)

        if args.command == "credential" and args.credential_command in {
            "grant",
            "revoke",
        }:
            return args.handler(
                args.sandbox_name,
                args.credential_name,
                args.confirmed,
            )

        if args.command == "credential" and args.credential_command == "get":
            return args.handler(args.name)

        if args.command == "credential" and args.credential_command == "list":
            return args.handler()

        return args.handler()

    except (
        OSError,
        RuntimeError,
        ValueError,
        SandboxError,
        CredentialError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
