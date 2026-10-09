from __future__ import annotations

import threading

from ..infrastructure.openshell.terminal import OpenShellTerminalSession
from .model import TerminalSessionInfo, TerminalSessionStatus


class TerminalRegistry:
    """Thread-safe registry with global and per-sandbox session quotas."""

    MAX_ACTIVE_SESSIONS = 16
    MAX_SESSIONS_PER_SANDBOX = 8
    MAX_RETAINED_SESSIONS = 256

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
            # Release dead stream objects and cap retained history for long-running servers.
            for terminal_id, existing_session in list(self._sessions.items()):
                if not existing_session.is_alive():
                    existing_info = self._info.get(terminal_id)
                    if existing_info is not None:
                        existing_info.status = (
                            TerminalSessionStatus.TERMINATED
                            if existing_session.error is None
                            else TerminalSessionStatus.ERROR
                        )
                        existing_info.exit_code = existing_session.exit_code
                        existing_info.error = existing_session.error
                    self._sessions.pop(terminal_id, None)
            while len(self._info) >= self.MAX_RETAINED_SESSIONS:
                oldest_inactive = next(
                    (terminal_id for terminal_id in self._info if terminal_id not in self._sessions),
                    None,
                )
                if oldest_inactive is None:
                    break
                self._info.pop(oldest_inactive, None)
            active = [
                current for terminal_id, current in self._info.items()
                if terminal_id in self._sessions and self._sessions[terminal_id].is_alive()
            ]
            sandbox_count = sum(current.sandbox == info.sandbox for current in active)
            if len(active) >= self.MAX_ACTIVE_SESSIONS:
                session.close()
                raise RuntimeError("Maximum active terminal session limit reached.")
            if sandbox_count >= self.MAX_SESSIONS_PER_SANDBOX:
                session.close()
                raise RuntimeError("Maximum active terminal sessions for this sandbox reached.")
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
