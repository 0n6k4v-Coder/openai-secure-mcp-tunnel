from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config.paths import APPLICATION_NAME, xdg_config_home, xdg_state_home

PROFILE_SCHEMA_VERSION = 1
PROFILE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
DEFAULT_PORT_BASE = 18080


class ProfileError(RuntimeError):
    """Raised when profile lifecycle management cannot proceed."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _deploy_root() -> Path:
    return _repository_root() / "deploy"


def _profiles_root() -> Path:
    return xdg_config_home() / APPLICATION_NAME / "profiles"


def _profiles_state_root() -> Path:
    return xdg_state_home() / APPLICATION_NAME / "profiles"


def _validate_name(name: str) -> str:
    if not PROFILE_NAME_PATTERN.fullmatch(name):
        raise ProfileError(
            "Profile names must start with a lowercase letter and contain only "
            "lowercase letters, digits, or hyphens (maximum 31 characters)."
        )
    return name


def _profile_root(name: str) -> Path:
    return _profiles_root() / _validate_name(name)


def _profile_state_root(name: str) -> Path:
    return _profiles_state_root() / _validate_name(name)


def _manifest_path(name: str) -> Path:
    return _profile_root(name) / "profile.json"


def _read_manifest(name: str) -> dict[str, object]:
    root = _profile_root(name)
    path = _manifest_path(name)
    if root.is_symlink() or not root.is_dir() or not path.is_file() or path.is_symlink():
        raise ProfileError(f"Profile '{name}' does not exist. Create it first.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"Cannot read profile manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ProfileError(f"Profile manifest has an unsupported format: {path}")
    return value


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _allocate_ports() -> dict[str, int]:
    used: set[int] = set()
    for manifest in list_profiles():
        ports = manifest.get("ports", {})
        if isinstance(ports, dict):
            used.update(value for value in ports.values() if isinstance(value, int))
    for gateway in range(DEFAULT_PORT_BASE, DEFAULT_PORT_BASE + 2000, 10):
        health, mcp = gateway + 1, gateway + 2
        candidate = (gateway, health, mcp)
        if not used.intersection(candidate) and all(
            _is_port_available(port) for port in candidate
        ):
            return {"gateway": gateway, "health": health, "mcp": mcp}
    raise ProfileError("No available profile ports found in the configured range.")


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _generate_profile_files(name: str) -> None:
    deploy = _deploy_root() / "openshell"
    toml_path = deploy / "gateway.toml"
    metadata_path = deploy / "gateway-metadata.json"
    if not toml_path.is_file() or not metadata_path.is_file():
        raise ProfileError("Profile templates are missing from deploy/openshell.")
    profile_root = _profile_root(name)
    toml = toml_path.read_text(encoding="utf-8").replace(
        'gateway_id = "openai-secure-mcp-tunnel"',
        f'gateway_id = "openai-secure-mcp-tunnel-{name}"',
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["name"] = "local"
    metadata["gateway_endpoint"] = "https://openshell-gateway:8080"
    _write_private(profile_root / "deploy" / "gateway.toml", toml)
    _write_private(
        profile_root / "deploy" / "gateway-metadata.json",
        json.dumps(metadata, indent=2) + "\n",
    )


def _profile_environment(name: str) -> dict[str, str]:
    manifest = _read_manifest(name)
    root = _profile_root(name)
    config_home = root / "xdg-config"
    state_home = _profile_state_root(name) / "xdg-state"
    ports = manifest.get("ports")
    if not isinstance(ports, dict):
        raise ProfileError(f"Profile '{name}' has invalid port configuration.")
    try:
        gateway, health, mcp = (
            int(ports[key]) for key in ("gateway", "health", "mcp")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProfileError(f"Profile '{name}' has invalid port configuration.") from exc
    state_app = state_home / APPLICATION_NAME
    return {
        "COMPOSE_PROJECT_NAME": str(manifest["project_name"]),
        "COMPOSE_FILE": str(_deploy_root() / "compose.yaml"),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_STATE_HOME": str(state_home),
        "MCP_PORT": str(mcp),
        "OPENSHELL_PORT": str(gateway),
        "OPENSHELL_HEALTH_PORT": str(health),
        "OPENSHELL_GATEWAY": "local",
        "OPENSHELL_CLI_GATEWAY": "https://openshell-gateway:8080",
        "MCP_CONFIG_DIR": str(state_app / "config"),
        "MCP_STATE_DIR": str(state_app / "mcp"),
        "WORKSPACE_GRANTS_DIR": str(state_app / "mcp" / "workspace-grants"),
        "MCP_GATEWAY_CONFIG_FILE": str(root / "deploy" / "gateway.toml"),
        "MCP_GATEWAY_METADATA_FILE": str(root / "deploy" / "gateway-metadata.json"),
    }


@contextmanager
def _temporary_environment(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _compose(name: str, *arguments: str) -> None:
    env = os.environ.copy()
    env.update(_profile_environment(name))
    command = [
        "docker", "compose", "--project-name", env["COMPOSE_PROJECT_NAME"],
        "-f", env["COMPOSE_FILE"], *arguments,
    ]
    try:
        result = subprocess.run(command, env=env, text=True, check=False)
    except FileNotFoundError as exc:
        raise ProfileError("Docker is required for profile runtime operations.") from exc
    if result.returncode:
        raise ProfileError(f"Docker Compose exited with status {result.returncode}.")


def create_profile(name: str) -> dict[str, object]:
    _validate_name(name)
    root = _profile_root(name)
    if root.exists() or root.is_symlink():
        raise ProfileError(f"Profile '{name}' already exists.")
    ports = _allocate_ports()
    state_root = _profile_state_root(name)
    manifest: dict[str, object] = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "name": name,
        "project_name": f"mcp-{name}",
        "ports": ports,
        "config_home": str(root / "xdg-config"),
        "state_home": str(state_root / "xdg-state"),
    }
    try:
        root.mkdir(parents=True, mode=0o700)
        os.chmod(root, 0o700)
        (root / "xdg-config").mkdir(mode=0o700)
        state_root.mkdir(parents=True, mode=0o700)
        os.chmod(state_root, 0o700)
        (state_root / "xdg-state").mkdir(mode=0o700)
        _generate_profile_files(name)
        _write_private(_manifest_path(name), json.dumps(manifest, indent=2) + "\n")
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return manifest


def list_profiles() -> list[dict[str, object]]:
    root = _profiles_root()
    if not root.is_dir():
        return []
    result: list[dict[str, object]] = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and not path.is_symlink():
            try:
                result.append(_read_manifest(path.name))
            except ProfileError:
                continue
    return result


def validate_profile(name: str) -> list[str]:
    _read_manifest(name)
    root = _profile_root(name)
    errors = [
        f"Missing profile resource: {relative}"
        for relative in (
            Path("deploy/gateway.toml"),
            Path("deploy/gateway-metadata.json"),
            Path("xdg-config"),
        )
        if not (root / relative).exists()
    ]
    if not (_profile_state_root(name) / "xdg-state").is_dir():
        errors.append("Missing profile state directory.")
    return errors


def _print_manifest(manifest: dict[str, object]) -> None:
    ports = manifest.get("ports", {})
    print(f"Profile: {manifest.get('name')}")
    print(f"Compose project: {manifest.get('project_name')}")
    if isinstance(ports, dict):
        print(f"Ports: gateway={ports.get('gateway')}, health={ports.get('health')}, mcp={ports.get('mcp')}")
    print(f"Config: {manifest.get('config_home')}")
    print(f"State: {manifest.get('state_home')}")


def _up(name: str) -> int:
    errors = validate_profile(name)
    if errors:
        raise ProfileError("Profile validation failed: " + "; ".join(errors))
    from . import lifecycle
    from ..infrastructure.openshell.tls import setup as setup_tls

    env = _profile_environment(name)
    with _temporary_environment(env):
        lifecycle.prepare_runtime()
        status = setup_tls()
        if not status.complete:
            raise ProfileError("OpenShell TLS setup did not complete.")
    _compose(name, "up", "--build", "-d", "openshell-gateway", "mcp-server")
    config_root = Path(env["XDG_CONFIG_HOME"]) / APPLICATION_NAME / "mcp-clients" / "openai"
    if (config_root / "config.yaml").is_file() and (config_root / "credentials").is_file():
        _compose(name, "up", "-d", "tunnel-client")
    print(f"Profile '{name}' core services started.")
    return 0


def _down(name: str) -> int:
    _read_manifest(name)
    _compose(name, "down")
    print(f"Profile '{name}' stopped; profile state was preserved.")
    return 0


def _cleanup_plan() -> int:
    profiles = list_profiles()
    print("Read-only cleanup plan; no files, grants, workspaces, or volumes are removed.")
    if not profiles:
        print("No managed profiles found.")
    for manifest in profiles:
        _print_manifest(manifest)
        print("Action: review manually; profile state and workspace grants are preserved.")
        print()
    return 0


def _uninstall(*, purge: bool, confirmed: bool) -> int:
    profiles = list_profiles()
    print(f"Managed profile configuration: {_profiles_root()}")
    print(f"Managed profile state: {_profiles_state_root()}")
    if not purge:
        print("Dry run only. Use --purge --yes to remove generated profile configuration.")
        print("Profile state, workspace grants, host workspaces, Docker volumes, and")
        print("the repository clone are never removed by this command.")
        return 0
    if not confirmed:
        raise ProfileError("Refusing purge without --yes.")
    for manifest in profiles:
        _compose(str(manifest["name"]), "down")
    root = _profiles_root()
    if root.exists():
        for path in root.iterdir():
            if path.is_dir() and not path.is_symlink() and (path / "profile.json").is_file():
                shutil.rmtree(path)
    print("Removed managed profile configuration. Profile state was preserved.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcpctl profile")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create an isolated profile.")
    create.add_argument("name")
    commands.add_parser("list", help="List managed profiles.")
    show = commands.add_parser("show", help="Show profile paths and ports.")
    show.add_argument("name")
    validate = commands.add_parser("validate", help="Validate generated files.")
    validate.add_argument("name")
    up = commands.add_parser("up", help="Prepare TLS and start the profile.")
    up.add_argument("name")
    down = commands.add_parser("down", help="Stop a profile without deleting data.")
    down.add_argument("name")
    cleanup = commands.add_parser("cleanup", help="Print a non-destructive cleanup plan.")
    cleanup.add_argument("--plan", action="store_true")
    uninstall = commands.add_parser("uninstall", help="Safely remove profile configuration.")
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.add_argument("--purge", action="store_true")
    uninstall.add_argument("--yes", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            _print_manifest(create_profile(args.name))
            return 0
        if args.command == "list":
            profiles = list_profiles()
            for manifest in profiles:
                _print_manifest(manifest)
                print()
            if not profiles:
                print("No managed profiles found.")
            return 0
        if args.command == "show":
            _print_manifest(_read_manifest(args.name))
            return 0
        if args.command == "validate":
            errors = validate_profile(args.name)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 2
            print(f"Profile '{args.name}' is valid.")
            return 0
        if args.command == "up":
            return _up(args.name)
        if args.command == "down":
            return _down(args.name)
        if args.command == "cleanup":
            return _cleanup_plan()
        if args.command == "uninstall":
            return _uninstall(purge=args.purge, confirmed=args.yes)
    except (OSError, ProfileError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error("unsupported command")
    return 2
