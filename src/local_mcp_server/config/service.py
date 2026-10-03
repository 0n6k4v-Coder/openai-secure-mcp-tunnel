from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

CONTROL_PLANE_TUNNEL_ID_PATTERN = re.compile(r"^tunnel_[0-9a-f]{32}$")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ENV_VALUE = os.environ.get("MCP_CONFIG_DIR")
if CONFIG_ENV_VALUE:
    _configured_root = Path(CONFIG_ENV_VALUE)
    CONFIG_ROOT = (
        (_configured_root if _configured_root.is_absolute() else PROJECT_ROOT / "deploy" / _configured_root)
        .resolve()
    )
else:
    CONFIG_ROOT = Path("/var/lib/local-mcp-server/config")

MCP_CLIENTS_ROOT = CONFIG_ROOT / "mcp-clients"
OPENAI_ROOT = MCP_CLIENTS_ROOT / "openai"
OPENAI_CONFIG_FILE = OPENAI_ROOT / "openai.yaml"
OPENAI_API_KEY_FILE = OPENAI_ROOT / "CONTROL_PLANE_API_KEY"
OPENAI_CONFIG_TEMPLATE = """\\
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

class ConfigError(RuntimeError):
    """Raised when application configuration is invalid or cannot be saved."""

def _validate_tunnel_id(value: str) -> str:
    tunnel_id = value.strip()
    if not CONTROL_PLANE_TUNNEL_ID_PATTERN.fullmatch(tunnel_id):
        raise ConfigError("CONTROL_PLANE_TUNNEL_ID must match 'tunnel_' followed by 32 lowercase hexadecimal characters.")
    return tunnel_id

def _validate_api_key(value: str) -> str:
    api_key = value.strip()
    if not api_key:
        raise ConfigError("CONTROL_PLANE_API_KEY must not be empty.")
    if "\\n" in api_key or "\\r" in api_key:
        raise ConfigError("CONTROL_PLANE_API_KEY must be a single line.")
    return api_key

def _atomic_write(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
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

def configure_openai(tunnel_id: str, api_key: str) -> None:
    validated_tunnel_id = _validate_tunnel_id(tunnel_id)
    validated_api_key = _validate_api_key(api_key)
    OPENAI_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    OPENAI_ROOT.chmod(0o700)
    config_content = OPENAI_CONFIG_TEMPLATE.format(tunnel_id=validated_tunnel_id)
    try:
        _atomic_write(OPENAI_API_KEY_FILE, f"{validated_api_key}\\n", mode=0o600)
        _atomic_write(OPENAI_CONFIG_FILE, config_content, mode=0o600)
    except OSError as exc:
        raise ConfigError(f"Unable to save OpenAI MCP client configuration: {exc}") from exc
