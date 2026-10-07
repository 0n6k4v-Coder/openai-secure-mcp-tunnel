from __future__ import annotations

import threading

from ..infrastructure.openshell.terminal import OpenShellTerminalSession
from .model import TerminalSessionInfo, TerminalSessionStatus


class TerminalRegistry:
    """Thread-safe registry of active terminal sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, OpenShellTerminalSession] = {}
        self._info: dict[str, TerminalSessionInfo] = {}
        self._lock = threading.Lock()

    def register(
        self,
        info: TerminalSessionInfo,
        session: OpenShellTerminalSession,
    ) -> None:
        with self._lock:
            self._info[info.terminal_id] = info
            self._sessions[info.terminal_id] = session

    def get_session(self, terminal_id: str) -> OpenShellTerminalSession | None:
        with self._lock:
            return self._sessions.get(terminal_id)

    def get_info(self, terminal_id: str) -> TerminalSessionInfo | None:
        with self._lock:
            info = self._info.get(terminal_id)
            session = self._sessions.get(terminal_id)
            if info and session:
                if not session.is_alive():
                    info.status = TerminalSessionStatus.TERMINATED if session.error is None else TerminalSessionStatus.ERROR
                    info.exit_code = session.exit_code
                    info.error = session.error
            return info

    def list_sessions(self, sandbox: str | None = None) -> list[TerminalSessionInfo]:
        with self._lock:
            results: list[TerminalSessionInfo] = []
            for tid, info in list(self._info.items()):
                session = self._sessions.get(tid)
                if session and not session.is_alive():
                    info.status = TerminalSessionStatus.TERMINATED if session.error is None else TerminalSessionStatus.ERROR
                    info.exit_code = session.exit_code
                    info.error = session.error
                if sandbox is None or info.sandbox == sandbox:
                    results.append(info)
            return results

    def unregister(self, terminal_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(terminal_id, None)
            info = self._info.pop(terminal_id, None)
            if session:
                session.close()
            return info is not None


_default_registry = TerminalRegistry()


def get_terminal_registry() -> TerminalRegistry:
    return _default_registry
