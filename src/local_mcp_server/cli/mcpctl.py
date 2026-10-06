from __future__ import annotations

import argparse
from builtins import input
import getpass
import json
import os
import shlex
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from ..config.paths import APPLICATION_NAME, xdg_config_home, xdg_state_home
from ..config.service import ConfigError, configure_openai
from ..infrastructure.openshell.tls import (
    OpenShellTLSStatusError,
    TLSStatus,
    get_status as get_openshell_tls_status,
    repair as repair_openshell_tls,
    setup as setup_openshell_tls,
)
from . import lifecycle
from .main import _print_table
from .main import main as local_mcp_server_main
from . import workspace_broker

EXIT_OK = 0
EXIT_ERROR = 2

SETUP_STEP_COUNT = 6


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


def _print_setup_step(
    number: int,
    title: str,
) -> None:
    print()
    print(f"[{number}/{SETUP_STEP_COUNT}] {title}")


def _print_setup_result(
    status: str,
) -> None:
    print(f"      {status}")


def _print_mcp_clients(
    statuses: tuple[lifecycle.MCPClientStatus, ...],
    *,
    include_runtime: bool,
) -> None:
    headers = ["#", "CLIENT", "CONFIGURATION"]

    if include_runtime:
        headers.append("RUNTIME")

    rows: list[list[str]] = []

    for index, client in enumerate(statuses, start=1):
        row = [
            str(index),
            client.display_name,
            ("✓ CONFIGURED" if client.configured else "○ NOT CONFIGURED"),
        ]

        if include_runtime:
            row.append(client.runtime)

        rows.append(row)

    _print_table(
        headers,
        rows,
    )


def _print_mcp_client_details(
    client: lifecycle.MCPClientStatus,
) -> None:
    print()
    print(f"{client.display_name} MCP Client")
    print()
    print(
        "Configuration:      "
        + ("✓ CONFIGURED" if client.configured else "○ NOT CONFIGURED")
    )
    print(
        "Config file:        "
        + ("✓ PRESENT" if client.config_present else "○ NOT FOUND")
    )
    print(
        "Credentials:        "
        + ("✓ PRESENT" if client.credentials_present else "○ NOT FOUND")
    )

    if client.permissions_secure is True:
        print("Permissions:        ✓ SECURE")
    elif client.permissions_secure is False:
        print("Permissions:        ✗ INSECURE")
    else:
        print("Permissions:        —")

    print("Runtime:            " + client.runtime)


def _configure_openai() -> int:
    print()
    print("OpenAI MCP Client")
    print()
    print("Configuration")
    print("  Enter the OpenAI tunnel credentials.")
    print()

    tunnel_id = input("CONTROL_PLANE_TUNNEL_ID: ").strip()
    api_key = getpass.getpass("CONTROL_PLANE_API_KEY: ")

    configure_openai(
        tunnel_id,
        api_key,
    )

    client = next(
        client
        for client in lifecycle.get_mcp_client_statuses()
        if client.key == "openai"
    )

    print()
    print("OpenAI MCP Client")
    print("  Configuration      ✓ CONFIGURED")
    print(
        "  Credentials        "
        + ("✓ PRESENT" if client.credentials_present else "✗ MISSING")
    )
    print(
        "  Permissions        "
        + ("✓ SECURE" if client.permissions_secure else "✗ INSECURE")
    )

    print()
    print("MCP client configuration saved.")

    return EXIT_OK


def _select_mcp_client(
    statuses: tuple[lifecycle.MCPClientStatus, ...],
    *,
    unconfigured_only: bool,
    allow_skip: bool,
) -> lifecycle.MCPClientStatus | None:
    candidates = tuple(
        client for client in statuses if not unconfigured_only or not client.configured
    )

    if not candidates:
        return None

    options = [client.display_name for client in candidates]

    if allow_skip:
        options.append("Skip for now")

    choice = _prompt_choice(
        (
            "Choose MCP clients to configure"
            if unconfigured_only
            else "Choose MCP client"
        ),
        options,
    )

    if allow_skip and choice == len(options):
        return None

    return candidates[choice - 1]


def _configure_selected_client(
    client: lifecycle.MCPClientStatus,
) -> int:
    if client.key == "openai":
        return _configure_openai()

    raise ValueError(f"Unsupported MCP client: {client.display_name}")


def _config_mcp_client(
    *,
    allow_skip: bool = False,
) -> int:
    statuses = lifecycle.get_mcp_client_statuses()

    print()
    print("MCP Clients")
    print()

    _print_mcp_clients(
        statuses,
        include_runtime=False,
    )

    if allow_skip:
        unconfigured = tuple(client for client in statuses if not client.configured)

        if not unconfigured:
            print()
            print("All MCP clients are configured.")
            return EXIT_OK

        print()

        selected = _select_mcp_client(
            statuses,
            unconfigured_only=True,
            allow_skip=True,
        )

        if selected is None:
            print()
            print("MCP client configuration skipped.")
            print("You can configure it later with:")
            print("  mcpctl config mcp-client")
            return EXIT_OK

        return _configure_selected_client(selected)

    selected = _select_mcp_client(
        statuses,
        unconfigured_only=False,
        allow_skip=False,
    )

    if selected is None:
        raise ValueError("No MCP clients are available.")

    _print_mcp_client_details(selected)

    action_options = (
        ["Configure", "Back"] if not selected.configured else ["Reconfigure", "Back"]
    )

    print()

    action = _prompt_choice(
        "Choose an action",
        action_options,
    )

    if action == 2:
        return EXIT_OK

    return _configure_selected_client(selected)


def _config() -> int:
    if (
        _prompt_choice(
            "Configuration",
            ["MCP Clients"],
        )
        != 1
    ):
        raise ValueError("Unsupported configuration selection.")

    return _config_mcp_client()


def _print_tls_status(status: TLSStatus) -> None:
    print("OpenShell TLS")
    print()
    print(f"State: {'✓ READY' if status.complete else '✗ NOT READY'}")
    print(f"Path: {status.root}")

    if status.missing:
        print()
        print("Missing:")

        for path in status.missing:
            print(f"  - {path.relative_to(status.root)}")

    if status.insecure_paths:
        print()
        print("Permissions:")

        for path in status.insecure_paths:
            print(f"  - {path.relative_to(status.root)}")


def _setup() -> int:
    print("Local MCP Server Setup")

    _print_setup_step(
        1,
        "Runtime",
    )

    lifecycle.prepare_runtime()

    _print_setup_result(
        "✓ READY",
    )

    _print_setup_step(
        2,
        "OpenShell TLS",
    )

    tls_status = setup_openshell_tls()

    _print_setup_result(
        "✓ READY" if tls_status.complete else "✗ NOT READY",
    )

    _print_setup_step(
        3,
        "MCP Clients",
    )

    _config_mcp_client(
        allow_skip=True,
    )

    _print_setup_step(
        4,
        "Docker Compose",
    )

    lifecycle.validate_compose()

    _print_setup_result(
        "✓ VALID",
    )

    _print_setup_step(
        5,
        "Core Services",
    )

    print("      OpenShell Gateway    … STARTING")
    print("      MCP Server           … STARTING")

    lifecycle.start_core_services()

    print("      OpenShell Gateway    ✓ READY")
    print("      MCP Server           ✓ READY")

    _print_setup_step(
        6,
        "Tunnel Client",
    )

    lifecycle.reconcile_tunnel_client()

    current_status = lifecycle.get_status(
        tls_status,
    )

    if current_status.tunnel_client.running:
        print("      OpenAI               ✓ ACTIVE")
    else:
        configured_clients = [
            client for client in current_status.mcp_clients if client.configured
        ]

        if configured_clients:
            print("      OpenAI               ○ NOT RUNNING")
        else:
            print("      OpenAI               — SKIPPED")

    final_status = lifecycle.verify(
        tls_status,
    )

    print()
    lifecycle.print_status(final_status)

    return EXIT_OK


def _status() -> int:
    tls_status = get_openshell_tls_status()
    status = lifecycle.get_status(tls_status)

    lifecycle.print_status(status)

    return EXIT_OK if status.ready else EXIT_ERROR


def _repair() -> int:
    print("Local MCP Server Repair")

    print()
    print("[1/5] Runtime")
    lifecycle.prepare_runtime()
    print("      ✓ READY")

    print()
    print("[2/5] OpenShell TLS")
    tls_status = repair_openshell_tls()
    print("      " + ("✓ READY" if tls_status.complete else "✗ NOT READY"))

    print()
    print("[3/5] Docker Compose")
    lifecycle.validate_compose()
    print("      ✓ VALID")

    print()
    print("[4/5] Core Services")
    print("      OpenShell Gateway    … STARTING")
    print("      MCP Server           … STARTING")

    lifecycle.start_core_services()

    print("      OpenShell Gateway    ✓ READY")
    print("      MCP Server           ✓ READY")

    print()
    print("[5/5] Tunnel Client")
    lifecycle.reconcile_tunnel_client()

    status = lifecycle.get_status(
        tls_status,
    )

    print("      " + ("✓ ACTIVE" if status.tunnel_client.running else "○ NOT RUNNING"))

    final_status = lifecycle.verify(
        tls_status,
    )

    print()
    lifecycle.print_status(final_status)

    return EXIT_OK


def _legacy_profile_roots() -> tuple[Path, Path]:
    config_root = xdg_config_home() / APPLICATION_NAME / "profiles"
    state_root = xdg_state_home() / APPLICATION_NAME / "profiles"
    return config_root, state_root


def _legacy_profile_configurations() -> list[Path]:
    config_root, _ = _legacy_profile_roots()

    if not config_root.is_dir() or config_root.is_symlink():
        return []

    return [
        child
        for child in sorted(config_root.iterdir())
        if child.is_dir()
        and not child.is_symlink()
        and (child / "profile.json").is_file()
        and not (child / "profile.json").is_symlink()
    ]


def _cleanup(*, json_output: bool = False) -> int:
    config_root, state_root = _legacy_profile_roots()
    configurations = _legacy_profile_configurations()
    payload = {
        "configuration_root": str(config_root),
        "state_root": str(state_root),
        "generated_configurations": [str(path) for path in configurations],
        "state_preserved": True,
        "workspace_grants_preserved": True,
        "host_workspaces_preserved": True,
        "docker_volumes_preserved": True,
        "repository_preserved": True,
        "destructive": False,
    }

    if json_output:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    print("Read-only legacy profile cleanup inventory")
    print(f"Generated configuration root: {config_root}")
    print(f"Legacy profile state root (preserved): {state_root}")
    print()
    if configurations:
        print("Generated profile configurations:")
        for path in configurations:
            print(f"  - {path}")
    else:
        print("No generated legacy profile configurations found.")
    print()
    print("No files, workspace grants, host workspaces, Docker volumes,")
    print("credentials, or runtime data were changed.")
    return EXIT_OK


def _purge_inventory() -> list[tuple[str, Path, str]]:
    """Return a path-only inventory; never read or print credential contents."""
    app_config_root = xdg_config_home() / APPLICATION_NAME
    app_state_root = xdg_state_home() / APPLICATION_NAME
    inventory: list[tuple[str, Path, str]] = [
        ("Application configuration", app_config_root, "REMOVE"),
        (
            "OpenAI MCP config",
            app_config_root / "mcp-clients" / "openai" / "config.yaml",
            "REMOVE",
        ),
        (
            "OpenAI MCP credentials (secret contents hidden)",
            app_config_root / "mcp-clients" / "openai" / "credentials",
            "REMOVE",
        ),
        ("Application state", app_state_root, "REMOVE"),
        (
            "Installation state",
            app_state_root / "mcp" / "installations.json",
            "REMOVE",
        ),
        (
            "Workspace grant records",
            app_state_root / "mcp" / "workspace-grants" / "workspace-grants.json",
            "REMOVE",
        ),
        (
            "Application OpenShell TLS",
            app_state_root / "openshell" / "tls",
            "REMOVE",
        ),
        (
            "OpenShell CLI mTLS bundle (outside app root; may be shared)",
            xdg_config_home() / "openshell" / "gateways" / "local" / "mtls",
            "PRESERVE",
        ),
    ]

    # Compose can be configured to mount data outside the standard XDG roots.
    # We deliberately report, but never delete, those externally owned paths.
    for variable in ("MCP_CONFIG_DIR", "MCP_STATE_DIR", "WORKSPACE_GRANTS_DIR"):
        value = os.environ.get(variable)
        if value:
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            standard_roots = (app_config_root, app_state_root)
            try:
                inside_app_roots = any(
                    candidate.resolve().is_relative_to(root.resolve())
                    for root in standard_roots
                )
            except (OSError, RuntimeError):
                inside_app_roots = False
            if not inside_app_roots:
                inventory.append(
                    (
                        f"{variable} override (outside purge scope)",
                        candidate,
                        "PRESERVE",
                    )
                )
    return inventory


def _path_status(path: Path) -> str:
    if path.is_symlink():
        return "FOUND (SYMLINK; NOT FOLLOWED)"
    if path.exists():
        return "FOUND"
    return "NOT FOUND"


def _uninstall(*, confirmed: bool, purge: bool = False) -> int:
    config_root, state_root = _legacy_profile_roots()
    configurations = _legacy_profile_configurations()
    app_config_root = xdg_config_home() / APPLICATION_NAME
    app_state_root = xdg_state_home() / APPLICATION_NAME

    if purge:
        inventory = _purge_inventory()
        print("Uninstall preflight inventory")
        print(
            f"Application configuration root: {app_config_root} "
            f"[{_path_status(app_config_root)}]"
        )
        print(
            f"Application state root: {app_state_root} [{_path_status(app_state_root)}]"
        )
        print()
        for label, path, action in inventory:
            status = _path_status(path)
            if action == "REMOVE":
                print(f"  {status} / WILL REMOVE: {label}: {path}")
            else:
                print(f"  {status} / PRESERVED / OUTSIDE SCOPE: {label}: {path}")

        print()
        print("Host workspaces, Docker volumes, and the repository are preserved.")
        print("OpenShell CLI mTLS files outside the application root are preserved.")
        print(
            "Custom Compose paths outside the application roots are preserved "
            "and must be reviewed separately."
        )

        if not confirmed:
            print()
            print("Dry run only; no files were removed.")
            print(
                "Review the inventory, then run "
                "'mcpctl uninstall --yes --purge' to execute."
            )
            return EXIT_OK

        # Never delete application state while this Compose project is running.
        # If Docker is installed but status cannot be determined, fail closed.
        if shutil.which("docker") is not None:
            try:
                service_statuses = lifecycle._service_statuses()
            except (OSError, RuntimeError, ValueError) as exc:
                print(
                    "PREFLIGHT FAILED: unable to determine Compose runtime state: "
                    f"{exc}",
                    file=sys.stderr,
                )
                print(
                    "No application data was removed. Check Docker, then retry.",
                    file=sys.stderr,
                )
                return EXIT_ERROR
            running = sorted(
                name for name, status in service_statuses.items() if status.running
            )
            if running:
                print(
                    "PREFLIGHT FAILED: application services are still running: "
                    + ", ".join(running),
                    file=sys.stderr,
                )
                print(
                    "No application data was removed. Run 'mcpctl stop' and retry.",
                    file=sys.stderr,
                )
                return EXIT_ERROR

        # Validate every deletion root before changing either root.
        roots = (app_config_root, app_state_root)
        for root in roots:
            if root.is_symlink():
                print(
                    "PREFLIGHT FAILED: refusing to purge symlinked application "
                    f"data root: {root}",
                    file=sys.stderr,
                )
                return EXIT_ERROR
            if root.exists() and not root.is_dir():
                print(
                    "PREFLIGHT FAILED: refusing to purge non-directory application "
                    f"data root: {root}",
                    file=sys.stderr,
                )
                return EXIT_ERROR

        results: list[tuple[Path, str]] = []
        for root in roots:
            if not root.exists():
                results.append((root, "ALREADY ABSENT"))
                continue
            try:
                shutil.rmtree(root)
                if root.exists() or root.is_symlink():
                    results.append((root, "FAILED (verification: path still exists)"))
                else:
                    results.append((root, "REMOVED (verified absent)"))
            except OSError as exc:
                results.append((root, f"FAILED ({type(exc).__name__}: {exc})"))
                if isinstance(exc, PermissionError):
                    print(
                        "RECOVERY: after stopping services and verifying that "
                        "this path contains no nested mounts, repair ownership "
                        "and retry:",
                        file=sys.stderr,
                    )
                    print(
                        "  sudo chown -R -- \"$(id -u):$(id -g)\" "
                        + shlex.quote(str(root)),
                        file=sys.stderr,
                    )
                    print(
                        "Do not run this against a path containing mounted or "
                        "shared data.",
                        file=sys.stderr,
                    )

        print()
        print("Uninstall result")
        for root, status in results:
            print(f"  {status}: {root}")
        failed = any(status.startswith("FAILED") for _, status in results)
        if failed:
            print(
                "PARTIAL FAILURE: inspect failed paths and rerun the command "
                "after resolving the issue.",
                file=sys.stderr,
            )
            return EXIT_ERROR
        print("Purge completed; both application roots are verified absent.")
        print("Preserved host workspaces, Docker volumes, and the repository.")
        return EXIT_OK

    print(f"Generated profile configuration root: {config_root}")
    print(f"Legacy profile state root (preserved): {state_root}")
    if not confirmed:
        print("Dry run only; no files were removed.")
        if configurations:
            print(
                "Would remove the following generated profile configuration "
                "directories:"
            )
            for path in configurations:
                print(f"  - {path}")
        else:
            print("No generated legacy profile configurations found.")
        print("Use 'mcpctl uninstall --yes' to remove only these generated")
        print(
            "configuration directories. Profile state and all other data are preserved."
        )
        return EXIT_OK

    removed: list[Path] = []
    failed: list[tuple[Path, str]] = []
    for path in configurations:
        # Re-check the generated marker immediately before deletion.
        marker = path / "profile.json"
        if (
            path.is_symlink()
            or not path.is_dir()
            or marker.is_symlink()
            or not marker.is_file()
        ):
            continue
        try:
            shutil.rmtree(path)
            if path.exists() or path.is_symlink():
                failed.append((path, "verification failed; path still exists"))
            else:
                removed.append(path)
        except OSError as exc:
            failed.append((path, f"{type(exc).__name__}: {exc}"))

    print("Removed generated legacy profile configuration directories:")
    if removed:
        for path in removed:
            print(f"  REMOVED (verified absent): {path}")
    else:
        print("  NOTHING TO DO")
    for path, reason in failed:
        print(f"  FAILED: {path}: {reason}", file=sys.stderr)
    print("Preserved profile state, workspace grants, host workspaces, credentials,")
    print("Docker volumes, central application configuration, and the repository.")
    return EXIT_ERROR if failed else EXIT_OK


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
        "start",
        help="Build and start the Compose stack.",
    )
    commands.add_parser(
        "stop",
        help="Stop and remove the Compose stack.",
    )
    commands.add_parser(
        "restart",
        help="Rebuild and recreate the Compose stack.",
    )
    compose_status = commands.add_parser(
        "compose-status",
        help="Show Docker Compose service status.",
    )
    compose_status.add_argument("--json", dest="json_output", action="store_true")

    logs = commands.add_parser(
        "logs",
        help="Show Docker Compose service logs.",
    )
    logs.add_argument(
        "service",
        nargs="?",
        choices=["openshell-gateway", "mcp-server", "tunnel-client"],
    )
    logs.add_argument("--follow", "-f", action="store_true")
    logs.add_argument("--tail", "-n", default="100")

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

    cleanup = commands.add_parser(
        "cleanup",
        help="Show a read-only inventory of legacy application-profile data.",
    )
    cleanup.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print the cleanup inventory as JSON.",
    )

    uninstall = commands.add_parser(
        "uninstall",
        help="Remove generated legacy profile configuration; retained state is preserved.",
    )
    uninstall_confirmation = uninstall.add_mutually_exclusive_group()
    uninstall_confirmation.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without changing files (the default).",
    )
    uninstall_confirmation.add_argument(
        "--yes",
        action="store_true",
        dest="confirmed",
        help="Confirm the requested uninstall operation.",
    )
    uninstall.add_argument(
        "--purge",
        action="store_true",
        help="Remove all application-owned configuration and state (requires --yes to execute).",
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

    workspace_source = sandbox_create.add_mutually_exclusive_group(required=True)
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
        "name",
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
        "name",
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

    credential_get.add_argument(
        "--key",
        required=True,
        dest="credential_key",
    )

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
        help="Output the public workspace schema as JSON.",
    )
    workspace_list.add_argument(
        "--verbose",
        action="store_true",
        help="Include internal workspace and infrastructure details.",
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
    return local_mcp_server_main([command, *arguments])


def _sandbox_arguments(
    args: argparse.Namespace,
) -> list[str]:
    if args.sandbox_command == "create":
        arguments = [
            "create",
            args.name,
        ]

        if args.standalone:
            arguments.append("--standalone")
        else:
            arguments.extend(["--workspace", args.workspace_id])

        arguments.extend(["--profile", args.profile])

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

    raise RuntimeError(f"Unsupported sandbox command: {args.sandbox_command}")


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
        raise RuntimeError(f"Unsupported credential command: {command}")

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
        if args.verbose:
            arguments.append("--verbose")

        return arguments

    raise RuntimeError(f"Unsupported workspace command: {command}")


def main(
    argv: list[str] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command in {"start", "stop", "restart"}:
            return _delegate_local_cli(args.command, [])

        if args.command == "compose-status":
            arguments = ["--json"] if args.json_output else []
            return _delegate_local_cli("status", arguments)

        if args.command == "logs":
            arguments = []
            if args.service is not None:
                arguments.append(args.service)
            if args.follow:
                arguments.append("--follow")
            arguments.extend(["--tail", args.tail])
            return _delegate_local_cli("logs", arguments)

        if args.command == "setup":
            return _setup()

        if args.command == "status":
            return _status()

        if args.command == "repair":
            return _repair()

        if args.command == "cleanup":
            return _cleanup(json_output=args.json_output)

        if args.command == "uninstall":
            return _uninstall(confirmed=args.confirmed, purge=args.purge)

        if args.command == "config":
            if args.config_command != "mcp-client":
                raise RuntimeError(f"Unsupported config command: {args.config_command}")

            if args.mcp_client_command is None:
                return _config_mcp_client()

            if args.mcp_client_command == "openai":
                return _configure_openai()

            raise RuntimeError(
                f"Unsupported MCP client command: {args.mcp_client_command}"
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
            return workspace_broker.main(_workspace_arguments(args))

        raise RuntimeError(f"Unsupported command: {args.command}")

    except KeyboardInterrupt:
        print(
            "\nCancelled.",
            file=sys.stderr,
        )
        return 130

    except (
        ConfigError,
        OSError,
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
