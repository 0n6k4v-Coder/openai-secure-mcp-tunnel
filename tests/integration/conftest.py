from __future__ import annotations

import asyncio
import inspect
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

T = TypeVar("T")


def _decode_tool_result(result: Any) -> Any:
    if result.is_error:
        raise AssertionError(f"MCP tool returned an error result: {result.content!r}")

    structured = result.structured_content

    if structured is not None:
        if isinstance(structured, dict) and set(structured) == {"result"}:
            value = structured["result"]
        else:
            value = structured

        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        return value

    for content in result.content:
        text = getattr(content, "text", None)

        if text is None:
            continue

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    return None


@dataclass(frozen=True)
class MCPIntegrationClient:
    url: str
    host_header: str

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        return asyncio.run(
            self._call_tool(
                name=name,
                arguments=arguments,
            )
        )

    def call_tool_expect_error(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        return asyncio.run(
            self._call_tool_expect_error(
                name=name,
                arguments=arguments,
            )
        )

    def run(
        self,
        operation: Callable[[Client], T | Awaitable[T]],
    ) -> T:
        return asyncio.run(self._run(operation))

    async def _call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> Any:
        async with self._client() as client:
            result = await client.call_tool(
                name,
                arguments,
            )
            return _decode_tool_result(result)

    async def _call_tool_expect_error(
        self,
        *,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> Any:
        async with self._client() as client:
            result = await client.call_tool(
                name,
                arguments,
            )
            assert result.is_error is True
            return result

    async def _run(
        self,
        operation: Callable[[Client], T | Awaitable[T]],
    ) -> T:
        async with self._client() as client:
            result = operation(client)
            if inspect.isawaitable(result):
                return await result
            return result

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Client]:
        async with httpx2.AsyncClient(
            headers={
                "Host": self.host_header,
                "Accept": "application/json, text/event-stream",
            },
            timeout=httpx2.Timeout(30.0, read=300.0),
        ) as http_client:
            transport = streamable_http_client(
                self.url,
                http_client=http_client,
            )
            async with Client(transport) as client:
                yield client


@pytest.fixture(scope="session")
def mcp_client() -> MCPIntegrationClient:
    if os.environ.get("RUN_MCP_INTEGRATION") != "1":
        pytest.skip("Set RUN_MCP_INTEGRATION=1 to run MCP integration tests.")

    return MCPIntegrationClient(
        url=os.environ.get(
            "MCP_INTEGRATION_URL",
            "http://127.0.0.1:8000/mcp",
        ),
        host_header=os.environ.get(
            "MCP_INTEGRATION_HOST",
            "mcp-server:8000",
        ),
    )
