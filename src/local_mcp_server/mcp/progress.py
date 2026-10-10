from __future__ import annotations

import asyncio
import inspect
import logging
from functools import partial, wraps
from inspect import Parameter, Signature
from typing import Any, Callable, TypeVar, cast

from mcp.server.mcpserver import Context

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)


async def _report_progress(
    ctx: Context,
    progress: float,
    total: float,
    message: str,
) -> None:
    """Report progress without allowing a notification failure to mask tool work."""
    try:
        await ctx.report_progress(
            progress=progress,
            total=total,
            message=message,
        )
    except Exception:
        logger.debug(
            "Unable to report MCP tool progress: %s",
            message,
            exc_info=True,
        )


def with_tool_progress(func: F) -> F:
    """Wrap a tool with start, completion, and failure progress notifications.

    The injected Context parameter is excluded from the model-visible input
    schema by the MCP SDK. Synchronous handlers run in a worker thread so
    the asynchronous event loop remains available for progress notifications.
    """
    original_signature = inspect.signature(func)

    if "ctx" in original_signature.parameters:
        raise ValueError(f"{func.__name__} already declares a 'ctx' parameter.")

    context_parameter = Parameter(
        "ctx",
        kind=Parameter.KEYWORD_ONLY,
        annotation=Context,
    )

    parameters = list(original_signature.parameters.values())
    keyword_variadic_index = next(
        (
            index
            for index, parameter in enumerate(parameters)
            if parameter.kind is Parameter.VAR_KEYWORD
        ),
        len(parameters),
    )
    parameters.insert(keyword_variadic_index, context_parameter)
    wrapped_signature = Signature(
        parameters=parameters,
        return_annotation=original_signature.return_annotation,
    )

    @wraps(func)
    async def wrapped(
        *args: Any,
        ctx: Context,
        **kwargs: Any,
    ) -> Any:
        tool_name = func.__name__

        await _report_progress(ctx, 0, 1, f"Running {tool_name}")

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = await asyncio.to_thread(partial(func, *args, **kwargs))
        except Exception:
            await _report_progress(ctx, 1, 1, f"{tool_name} failed")
            raise

        await _report_progress(ctx, 1, 1, f"{tool_name} completed")
        return result

    wrapped.__signature__ = wrapped_signature  # type: ignore[attr-defined]
    wrapped.__annotations__ = {
        **getattr(func, "__annotations__", {}),
        "ctx": Context,
    }
    return cast(F, wrapped)
