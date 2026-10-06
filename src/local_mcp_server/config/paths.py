from __future__ import annotations

import os
from pathlib import Path

APPLICATION_NAME = "local-mcp-server"


def _xdg_base_directory(
    environment_variable: str,
    default_directory: str,
) -> Path:
    value = os.environ.get(environment_variable)

    if value:
        candidate = Path(value).expanduser()

        if candidate.is_absolute():
            return candidate

    return Path.home() / default_directory


def xdg_config_home() -> Path:
    return _xdg_base_directory(
        "XDG_CONFIG_HOME",
        ".config",
    )


def xdg_state_home() -> Path:
    return _xdg_base_directory(
        "XDG_STATE_HOME",
        ".local/state",
    )


def app_config_root() -> Path:
    from ..runtime.context import get_runtime_context
    return get_runtime_context().config_root


def app_state_root() -> Path:
    from ..runtime.context import get_runtime_context
    return get_runtime_context().state_root


def mcp_clients_root() -> Path:
    return app_config_root() / "mcp-clients"


def openai_root() -> Path:
    return mcp_clients_root() / "openai"


def openai_config_file() -> Path:
    return openai_root() / "config.yaml"


def openai_api_key_file() -> Path:
    return openai_root() / "credentials"


def mcp_state_root() -> Path:
    return app_state_root() / "mcp"


def installation_state_file() -> Path:
    return mcp_state_root() / "installations.json"


def workspace_grants_root() -> Path:
    return mcp_state_root() / "workspace-grants"


def workspace_grants_file() -> Path:
    return workspace_grants_root() / "workspace-grants.json"
