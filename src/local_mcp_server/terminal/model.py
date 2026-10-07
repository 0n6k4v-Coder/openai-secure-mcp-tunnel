from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TerminalSessionStatus(str, Enum):
    INITIALIZING = "initializing"
    ACTIVE = "active"
    TERMINATED = "terminated"
    ERROR = "error"


@dataclass
class TerminalSessionInfo:
    terminal_id: str
    sandbox: str
    command: list[str]
    cols: int
    rows: int
    created_at: str
    status: TerminalSessionStatus
    exit_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "terminal_id": self.terminal_id,
            "sandbox": self.sandbox,
            "command": self.command,
            "cols": self.cols,
            "rows": self.rows,
            "created_at": self.created_at,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "error": self.error,
            "metadata": self.metadata,
        }
