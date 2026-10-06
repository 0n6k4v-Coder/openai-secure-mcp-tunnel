from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .model import RuntimeProfile
from .registry import load_runtime


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    profile: RuntimeProfile
    config_home: Path
    state_home: Path

    @property
    def is_default(self) -> bool:
        return self.profile.name == "default"

    @property
    def config_root(self) -> Path:
        if self.is_default:
            return self.config_home / "local-mcp-server"
        return self.config_home / "local-mcp-server" / "runtimes" / self.profile.name

    @property
    def state_root(self) -> Path:
        if self.is_default:
            return self.state_home / "local-mcp-server"
        return self.state_home / "local-mcp-server" / "runtimes" / self.profile.name

    def child_environment(self, base: dict[str, str] | None = None) -> dict[str, str]:
        environment = dict(os.environ if base is None else base)
        environment["MCP_RUNTIME"] = self.profile.name
        environment["OPENSHELL_WORKSPACE"] = self.profile.openshell_workspace
        environment["COMPOSE_PROJECT_NAME"] = self.profile.compose_project_name
        if not self.is_default:
            environment["XDG_CONFIG_HOME"] = str(self.config_home)
            environment["XDG_STATE_HOME"] = str(self.state_home)
        return environment


def _xdg_home(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable)
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return candidate
    return Path.home() / fallback


def get_runtime_context(name: str | None = None) -> RuntimeContext:
    runtime_name = name or os.environ.get("MCP_RUNTIME", "default")
    profile = load_runtime(runtime_name)
    return RuntimeContext(
        profile=profile,
        config_home=_xdg_home("XDG_CONFIG_HOME", ".config"),
        state_home=_xdg_home("XDG_STATE_HOME", ".local/state"),
    )
