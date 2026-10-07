from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..runtime.context import get_runtime_context

VALID_CAPABILITIES = {"docker", "openshell"}


class CapabilityError(RuntimeError):
    """Raised when capability operation fails."""


@dataclass
class CapabilityRecord:
    capability: str
    sandbox: str
    granted_at: str
    expires_at: str | None = None
    mode: str = "isolated"
    metadata: dict[str, Any] = field(default_factory=dict)


def _get_state_path() -> Path:
    context = get_runtime_context()
    base = context.state_root
    base.mkdir(parents=True, exist_ok=True)
    return base / "capabilities.json"


def _load_data() -> dict[str, Any]:
    path = _get_state_path()
    if not path.is_file():
        return {
            "grants": {},
            "stats": {
                "lifetime_grants": {"docker": 0, "openshell": 0},
                "peak_concurrent": {"docker": 0, "openshell": 0},
            },
        }
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "grants": {},
            "stats": {
                "lifetime_grants": {"docker": 0, "openshell": 0},
                "peak_concurrent": {"docker": 0, "openshell": 0},
            },
        }


def _save_data(data: dict[str, Any]) -> None:
    path = _get_state_path()
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp_path.replace(path)


def _cleanup_expired(data: dict[str, Any]) -> bool:
    now = time.time()
    grants = data.get("grants", {})
    modified = False
    for _, sandboxes in list(grants.items()):
        for sandbox, record in list(sandboxes.items()):
            exp = record.get("expires_timestamp")
            if exp is not None and exp <= now:
                del sandboxes[sandbox]
                modified = True
    return modified


def grant_capability(
    sandbox_name: str,
    capability: str,
    ttl_seconds: int | None = None,
    mode: str = "isolated",
) -> dict[str, Any]:
    if capability not in VALID_CAPABILITIES:
        raise CapabilityError(
            f"Invalid capability '{capability}'. Supported: {', '.join(sorted(VALID_CAPABILITIES))}"
        )

    data = _load_data()
    _cleanup_expired(data)
    grants = data.setdefault("grants", {}).setdefault(capability, {})

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    expires_iso = None
    expires_ts = None

    if ttl_seconds is not None and ttl_seconds > 0:
        expires_ts = time.time() + ttl_seconds
        expires_iso = datetime.fromtimestamp(expires_ts, timezone.utc).isoformat()

    context = get_runtime_context()
    metadata: dict[str, Any] = {}
    if capability == "docker":
        metadata["mode"] = mode
        metadata["socket"] = f"/var/run/mcpctl/sandboxes/{sandbox_name}/docker.sock"
    elif capability == "openshell":
        target_port = context.profile.openshell_port if not context.is_default else 2223
        metadata["gateway"] = f"127.0.0.1:{target_port}"
        metadata["runtime"] = context.profile.name

    record = {
        "capability": capability,
        "sandbox": sandbox_name,
        "granted_at": now_iso,
        "expires_at": expires_iso,
        "expires_timestamp": expires_ts,
        "metadata": metadata,
    }

    is_new = sandbox_name not in grants
    grants[sandbox_name] = record

    # Update stats
    stats = data.setdefault("stats", {})
    lifetime = stats.setdefault("lifetime_grants", {"docker": 0, "openshell": 0})
    peak = stats.setdefault("peak_concurrent", {"docker": 0, "openshell": 0})

    if is_new:
        lifetime[capability] = lifetime.get(capability, 0) + 1

    current_count = len(grants)
    if current_count > peak.get(capability, 0):
        peak[capability] = current_count

    _save_data(data)
    return record


def revoke_capability(
    sandbox_name: str,
    capability: str,
    purge_data: bool = False,
) -> bool:
    if capability not in VALID_CAPABILITIES:
        raise CapabilityError(
            f"Invalid capability '{capability}'. Supported: {', '.join(sorted(VALID_CAPABILITIES))}"
        )

    data = _load_data()
    _cleanup_expired(data)
    grants = data.setdefault("grants", {}).setdefault(capability, {})

    if sandbox_name not in grants:
        return False

    del grants[sandbox_name]
    _save_data(data)
    return True


def list_capabilities(sandbox_name: str | None = None) -> dict[str, Any]:
    data = _load_data()
    if _cleanup_expired(data):
        _save_data(data)

    grants = data.get("grants", {})
    if sandbox_name is None:
        return grants

    result: dict[str, Any] = {}
    for cap, sboxes in grants.items():
        if sandbox_name in sboxes:
            result[cap] = sboxes[sandbox_name]
    return result


def get_capability_stats() -> dict[str, Any]:
    data = _load_data()
    if _cleanup_expired(data):
        _save_data(data)

    grants = data.get("grants", {})
    stats = data.get("stats", {})

    active_counts = {
        cap: len(grants.get(cap, {})) for cap in VALID_CAPABILITIES
    }

    return {
        "active_grants": active_counts,
        "peak_concurrent": stats.get("peak_concurrent", {"docker": 0, "openshell": 0}),
        "lifetime_grants": stats.get("lifetime_grants", {"docker": 0, "openshell": 0}),
    }


def inspect_sandbox_capabilities(sandbox_name: str) -> dict[str, Any]:
    """Inspection output formatted for MCP Tool exposure to LLMs."""
    granted_caps = list_capabilities(sandbox_name)
    capabilities_status: dict[str, Any] = {}

    for cap in sorted(VALID_CAPABILITIES):
        if cap in granted_caps:
            rec = granted_caps[cap]
            capabilities_status[cap] = {
                "granted": True,
                "metadata": rec.get("metadata", {}),
                "expires_at": rec.get("expires_at"),
            }
        else:
            capabilities_status[cap] = {
                "granted": False,
            }

    return {
        "sandbox": sandbox_name,
        "capabilities": capabilities_status,
    }
