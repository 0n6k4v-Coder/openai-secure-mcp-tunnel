"""Capability domain package for sandbox privilege management."""
from __future__ import annotations

from .service import (
    CapabilityError,
    get_capability_stats,
    grant_capability,
    inspect_sandbox_capabilities,
    list_capabilities,
    revoke_capability,
)

__all__ = [
    "CapabilityError",
    "get_capability_stats",
    "grant_capability",
    "inspect_sandbox_capabilities",
    "list_capabilities",
    "revoke_capability",
]
