from __future__ import annotations

from typing import Any


class LocalMCPError(Exception):
    """Base exception for actionable MCP domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "DOMAIN_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_tool_error_text(self) -> str:
        return self.message


class SandboxNotReadyError(LocalMCPError):
    """Raised when an operation targets a sandbox that is not ready or stopped."""

    def __init__(self, sandbox_name: str, hint: str | None = None) -> None:
        msg = f"Sandbox '{sandbox_name}' is not ready."
        if hint:
            msg += f" {hint}"
        super().__init__(msg, code="SANDBOX_NOT_READY")


class TargetContentNotFoundError(LocalMCPError):
    """Raised when target content is not found in file or window."""

    def __init__(
        self,
        message: str,
        start_line: int | None = None,
        end_line: int | None = None,
        occurrences: int = 0,
    ) -> None:
        details = {"start_line": start_line, "end_line": end_line, "occurrences": occurrences}
        super().__init__(message, code="TARGET_NOT_FOUND", details=details)


class CommandExecutionError(LocalMCPError):
    """Raised when a sandbox command fails."""

    def __init__(self, message: str, return_code: int = 1) -> None:
        super().__init__(message, code="COMMAND_EXECUTION_ERROR", details={"return_code": return_code})
