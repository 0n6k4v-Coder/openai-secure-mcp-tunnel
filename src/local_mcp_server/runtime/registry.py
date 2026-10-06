from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from .model import RuntimeProfile, validate_runtime_name

class RuntimeRegistryError(RuntimeError):
    """Raised when runtime registry operations fail safely."""


def _registry_path() -> Path:
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))).expanduser()
    if not xdg.is_absolute():
        xdg = Path.home() / ".config"
    return xdg / "local-mcp-server" / "runtimes.json"


def _read_registry() -> dict[str, RuntimeProfile]:
    path = _registry_path()
    if path.is_symlink():
        raise RuntimeRegistryError("Runtime registry must not be a symlink.")
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeRegistryError("Runtime registry could not be read.") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("runtimes"), list):
        raise RuntimeRegistryError("Runtime registry has an unsupported format.")
    result: dict[str, RuntimeProfile] = {}
    try:
        for item in raw["runtimes"]:
            profile = RuntimeProfile.from_dict(item)
            if profile.name == "default" or profile.name in result:
                raise ValueError("Duplicate or reserved runtime.")
            result[profile.name] = profile
    except (TypeError, ValueError) as exc:
        raise RuntimeRegistryError("Runtime registry contains an invalid entry.") from exc
    return result


def _write_registry(profiles: dict[str, RuntimeProfile]) -> None:
    path = _registry_path()
    if path.is_symlink():
        raise RuntimeRegistryError("Runtime registry must not be a symlink.")
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        fd, temp_name = tempfile.mkstemp(prefix=".runtimes.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    {"schema_version": 1, "runtimes": [p.to_dict() for p in sorted(profiles.values(), key=lambda p: p.name)]},
                    stream, indent=2, sort_keys=True,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    except OSError as exc:
        raise RuntimeRegistryError("Runtime registry could not be saved.") from exc


def list_runtimes() -> tuple[RuntimeProfile, ...]:
    return (RuntimeProfile.default(), *_read_registry().values())


def load_runtime(name: str) -> RuntimeProfile:
    if name == "default":
        return RuntimeProfile.default()
    try:
        validate_runtime_name(name)
    except ValueError as exc:
        raise RuntimeRegistryError(str(exc)) from exc
    try:
        return _read_registry()[name]
    except KeyError as exc:
        raise RuntimeRegistryError(f"Runtime {name!r} is not registered.") from exc


def create_runtime(name: str, description: str = "") -> RuntimeProfile:
    try:
        profile = RuntimeProfile.named(name, description)
    except ValueError as exc:
        raise RuntimeRegistryError(str(exc)) from exc
    profiles = _read_registry()
    if name in profiles:
        raise RuntimeRegistryError(f"Runtime {name!r} already exists.")
    profiles[name] = profile
    _write_registry(profiles)
    return profile


def delete_runtime(name: str) -> None:
    try:
        validate_runtime_name(name)
    except ValueError as exc:
        raise RuntimeRegistryError(str(exc)) from exc
    profiles = _read_registry()
    if name not in profiles:
        raise RuntimeRegistryError(f"Runtime {name!r} is not registered.")
    del profiles[name]
    _write_registry(profiles)
