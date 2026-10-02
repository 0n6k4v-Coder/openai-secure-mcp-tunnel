from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstallationRequest:
    request_id: str
    sandbox_name: str
    tool_name: str
    version: str
    source: str
    install_command: str
    reason: str
    created_at: str
