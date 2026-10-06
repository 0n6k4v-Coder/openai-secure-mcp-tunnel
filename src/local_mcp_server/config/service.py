from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path

from .paths import (
    app_config_root,
    mcp_clients_root,
    openai_api_key_file,
    openai_config_file,
    openai_root,
)

CONTROL_PLANE_TUNNEL_ID_PATTERN = re.compile(
    r"^tunnel_[0-9a-f]{32}$",
)


class ConfigError(RuntimeError):
    """Raised when application configuration is invalid or cannot be saved."""


CONFIG_ROOT = app_config_root()
MCP_CLIENTS_ROOT = mcp_clients_root()

OPENAI_ROOT = openai_root()
OPENAI_CONFIG_FILE = openai_config_file()
OPENAI_API_KEY_FILE = openai_api_key_file()

OPENAI_CONFIG_TEMPLATE = """\
config_version: 1
control_plane:
  base_url: https://api.openai.com
  tunnel_id: "{tunnel_id}"
  api_key: file:/run/secrets/CONTROL_PLANE_API_KEY
mcp:
  server_urls:
    - channel: main
      url: http://mcp-server:8000/mcp
"""


def _validate_tunnel_id(value: str) -> str:
    tunnel_id = value.strip()

    if not CONTROL_PLANE_TUNNEL_ID_PATTERN.fullmatch(tunnel_id):
        raise ConfigError(
            "CONTROL_PLANE_TUNNEL_ID must match "
            "'tunnel_' followed by 32 lowercase hexadecimal characters.",
        )

    return tunnel_id


def _validate_api_key(value: str) -> str:
    api_key = value.strip()

    if not api_key:
        raise ConfigError(
            "CONTROL_PLANE_API_KEY must not be empty.",
        )

    if "\n" in api_key or "\r" in api_key:
        raise ConfigError(
            "CONTROL_PLANE_API_KEY must be a single line.",
        )

    return api_key


def _ensure_private_directory(path: Path) -> None:
    try:
        path.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise ConfigError(
            f"Unable to prepare configuration directory {path}: {exc}",
        ) from exc

    if mode & 0o077:
        raise ConfigError(
            f"Configuration directory {path} must not be accessible "
            f"by group or other users; current mode is {mode:04o}.",
        )


def _atomic_write(
    path: Path,
    content: str,
    *,
    mode: int,
) -> None:
    _ensure_private_directory(path.parent)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)

    try:
        os.chmod(temporary_path, mode)

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)
        os.chmod(path, mode)

    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def configure_openai(
    tunnel_id: str,
    api_key: str,
) -> None:
    validated_tunnel_id = _validate_tunnel_id(tunnel_id)
    validated_api_key = _validate_api_key(api_key)
    if os.environ.get("MCP_RUNTIME", "default") == "default":
        config_root, clients_root, openai_root_path = CONFIG_ROOT, MCP_CLIENTS_ROOT, OPENAI_ROOT
        api_key_file, config_file = OPENAI_API_KEY_FILE, OPENAI_CONFIG_FILE
    else:
        from .paths import app_config_root as current_app_config_root, mcp_clients_root as current_mcp_clients_root, openai_api_key_file as current_openai_api_key_file, openai_config_file as current_openai_config_file, openai_root as current_openai_root
        config_root = current_app_config_root()
        clients_root = current_mcp_clients_root()
        openai_root_path = current_openai_root()
        api_key_file = current_openai_api_key_file()
        config_file = current_openai_config_file()
    config_content = OPENAI_CONFIG_TEMPLATE.format(tunnel_id=validated_tunnel_id)

    try:
        _ensure_private_directory(config_root)
        _ensure_private_directory(clients_root)
        _ensure_private_directory(openai_root_path)

        _atomic_write(
            api_key_file,
            f"{validated_api_key}\n",
            mode=0o600,
        )
        _atomic_write(
            config_file,
            config_content,
            mode=0o600,
        )

    except ConfigError:
        raise
    except OSError as exc:
        raise ConfigError(
            f"Unable to save OpenAI MCP client configuration: {exc}",
        ) from exc
