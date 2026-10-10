from __future__ import annotations

from functools import wraps
import inspect
from typing import Any, Callable, TypeVar

from mcp.server.mcpserver.exceptions import ToolError
from .exceptions import LocalMCPError

F = TypeVar("F", bound=Callable[..., Any])


def domain_tool(func: F) -> F:
    """
    Decorator that normalizes domain exceptions into actionable FastMCP ToolErrors.
    Ensures unit tests, direct calls, and MCP transport share uniform error semantics.
    """
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except ToolError:
                raise
            except LocalMCPError as exc:
                raise ToolError(exc.to_tool_error_text()) from exc
            except (ValueError, FileNotFoundError) as exc:
                raise ToolError(str(exc)) from exc
            except Exception as exc:
                raise ToolError(str(exc)) from exc

        return async_wrapper  # type: ignore[return-value]

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ToolError:
            raise
        except LocalMCPError as exc:
            raise ToolError(exc.to_tool_error_text()) from exc
        except (ValueError, FileNotFoundError) as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            raise ToolError(str(exc)) from exc

    return sync_wrapper  # type: ignore[return-value]
