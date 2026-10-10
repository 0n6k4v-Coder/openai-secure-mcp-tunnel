from __future__ import annotations

import inspect

import pytest
from mcp.server.mcpserver import Context

from local_mcp_server.mcp.progress import with_tool_progress


class RecordingContext:
    def __init__(self) -> None:
        self.events: list[tuple[float, float | None, str | None]] = []

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        self.events.append((progress, total, message))


@pytest.mark.anyio
async def test_sync_tool_reports_start_and_completion() -> None:
    def sample_tool(value: int) -> int:
        return value * 2

    instrumented = with_tool_progress(sample_tool)
    context = RecordingContext()

    result = await instrumented(value=21, ctx=context)

    assert result == 42
    assert context.events == [
        (0, 1, "Running sample_tool"),
        (1, 1, "sample_tool completed"),
    ]


@pytest.mark.anyio
async def test_async_tool_reports_start_and_completion() -> None:
    async def sample_tool(value: str) -> str:
        return value.upper()

    instrumented = with_tool_progress(sample_tool)
    context = RecordingContext()

    result = await instrumented(value="ready", ctx=context)

    assert result == "READY"
    assert context.events == [
        (0, 1, "Running sample_tool"),
        (1, 1, "sample_tool completed"),
    ]


@pytest.mark.anyio
async def test_failed_tool_reports_failure_and_preserves_exception() -> None:
    def sample_tool() -> None:
        raise ValueError("expected test failure")

    instrumented = with_tool_progress(sample_tool)
    context = RecordingContext()

    with pytest.raises(ValueError, match="expected test failure"):
        await instrumented(ctx=context)

    assert context.events == [
        (0, 1, "Running sample_tool"),
        (1, 1, "sample_tool failed"),
    ]


def test_context_is_injected_without_replacing_tool_arguments() -> None:
    def sample_tool(value: int, enabled: bool = True) -> int:
        return value if enabled else 0

    instrumented = with_tool_progress(sample_tool)
    signature = inspect.signature(instrumented)

    assert signature.parameters["value"].annotation == "int"
    assert signature.parameters["enabled"].default is True
    assert signature.parameters["ctx"].annotation is Context
    assert signature.parameters["ctx"].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.get_annotations(instrumented)["ctx"] is Context
