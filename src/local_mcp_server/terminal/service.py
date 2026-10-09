from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..infrastructure.openshell.sandbox import validate_name
from ..infrastructure.openshell.terminal import OpenShellTerminalSession
from .model import TerminalSessionInfo, TerminalSessionStatus
from .registry import get_terminal_registry


class TerminalError(RuntimeError):
    """Raised when a terminal operation fails."""


def open_terminal(
    sandbox: str,
    command: list[str] | None = None,
    cols: int = 80,
    rows: int = 24,
) -> dict[str, Any]:
    sandbox = validate_name(sandbox)
    cmd = command or ["sh", "-l"]
    if isinstance(cols, bool) or not isinstance(cols, int) or not 20 <= cols <= 300:
        raise TerminalError("Terminal columns must be between 20 and 300.")
    if isinstance(rows, bool) or not isinstance(rows, int) or not 5 <= rows <= 200:
        raise TerminalError("Terminal rows must be between 5 and 200.")
    terminal_id = str(uuid.uuid4())

    session = OpenShellTerminalSession(
        sandbox=sandbox,
        command=cmd,
        cols=cols,
        rows=rows,
    )
    session.start()

    info = TerminalSessionInfo(
        terminal_id=terminal_id,
        sandbox=sandbox,
        command=cmd,
        cols=cols,
        rows=rows,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=TerminalSessionStatus.ACTIVE,
    )

    registry = get_terminal_registry()
    try:
        registry.register(info, session)
    except RuntimeError as exc:
        session.close()
        raise TerminalError(str(exc)) from exc

    return info.to_dict()


def write_terminal(terminal_id: str, data: str) -> dict[str, Any]:
    registry = get_terminal_registry()
    session = registry.get_session(terminal_id)
    if session is None:
        raise TerminalError(f"Terminal session '{terminal_id}' not found.")

    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    if len(raw) > 64 * 1024:
        raise TerminalError("Terminal input exceeds the 64 KiB per-write limit.")
    try:
        session.write(data)
    except Exception as exc:
        raise TerminalError(str(exc)) from exc
    return {"terminal_id": terminal_id, "bytes_written": len(raw)}


def resize_terminal(terminal_id: str, cols: int, rows: int) -> dict[str, Any]:
    registry = get_terminal_registry()
    session = registry.get_session(terminal_id)
    if session is None:
        raise TerminalError(f"Terminal session '{terminal_id}' not found.")

    if isinstance(cols, bool) or not isinstance(cols, int) or not 20 <= cols <= 300:
        raise TerminalError("Terminal columns must be between 20 and 300.")
    if isinstance(rows, bool) or not isinstance(rows, int) or not 5 <= rows <= 200:
        raise TerminalError("Terminal rows must be between 5 and 200.")
    session.resize(cols=cols, rows=rows)
    info = registry.get_info(terminal_id)
    if info:
        info.cols = cols
        info.rows = rows
    return {"terminal_id": terminal_id, "cols": cols, "rows": rows}


def get_terminal_state(terminal_id: str, clear_buffer: bool = True) -> dict[str, Any]:
    registry = get_terminal_registry()
    session = registry.get_session(terminal_id)
    info = registry.get_info(terminal_id)
    if session is None or info is None:
        raise TerminalError(f"Terminal session '{terminal_id}' not found.")

    output_bytes = session.read_output(clear=clear_buffer)
    output_text = output_bytes.decode("utf-8", errors="replace")

    res = info.to_dict()
    res["output"] = output_text
    return res


def close_terminal(terminal_id: str) -> dict[str, Any]:
    registry = get_terminal_registry()
    info = registry.get_info(terminal_id)
    if info is None:
        raise TerminalError(f"Terminal session '{terminal_id}' not found.")

    registry.unregister(terminal_id)
    info.status = TerminalSessionStatus.TERMINATED
    return info.to_dict()


def list_terminals(sandbox: str | None = None) -> list[dict[str, Any]]:
    registry = get_terminal_registry()
    sessions = registry.list_sessions(sandbox=sandbox)
    return [s.to_dict() for s in sessions]
