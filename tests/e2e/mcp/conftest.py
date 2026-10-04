from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

MCP_TRANSPORT_TEST_IDS = tuple(f"MCP-TRANSPORT-{number:03d}" for number in range(1, 21))
MCP_HEALTH_TEST_IDS = tuple(f"MCP-HEALTH-{number:03d}" for number in range(1, 9))
MCP_REG_TEST_IDS = tuple(f"MCP-REG-{number:03d}" for number in range(1, 13))
MCP_TEST_ID_GROUPS = {
    "TRANSPORT": MCP_TRANSPORT_TEST_IDS,
    "HEALTH": MCP_HEALTH_TEST_IDS,
    "REG": MCP_REG_TEST_IDS,
}
MCP_E2E_TEST_IDS = tuple(
    test_id for group in MCP_TEST_ID_GROUPS.values() for test_id in group
)
VALID_STATUSES = {"Not implemented", "Blocked", "Pass", "Fail", "Skipped"}
STATUS_ICONS = {
    "Not implemented": "⚪",
    "Blocked": "🟠",
    "Pass": "🟢",
    "Fail": "🔴",
    "Skipped": "🟡",
}
TEST_ID_PATTERN = re.compile(r"MCP[-_](TRANSPORT|HEALTH|REG)[-_](\d{3})")


def _test_id(node_id: str) -> str | None:
    match = TEST_ID_PATTERN.search(node_id)
    if match is None:
        return None
    test_id = f"MCP-{match.group(1)}-{match.group(2)}"
    return test_id if test_id in MCP_E2E_TEST_IDS else None


def _status_for_reports(reports: list[pytest.TestReport]) -> str:
    if not reports:
        return "Not implemented"
    if any(report.failed for report in reports):
        return "Fail"
    skipped = [report for report in reports if report.skipped]
    if skipped:
        if any("BLOCKED:" in str(report.longrepr) for report in skipped):
            return "Blocked"
        return "Skipped"
    if all(report.passed for report in reports):
        return "Pass"
    return "Not implemented"


def _update_mcp_report(statuses: dict[str, str]) -> None:
    report_path = Path(__file__).resolve().parents[1] / "reports" / "mcp.md"
    if not report_path.is_file():
        raise FileNotFoundError(f"MCP E2E report does not exist: {report_path}")

    lines = report_path.read_text(encoding="utf-8").splitlines()
    row_indexes: dict[str, list[int]] = {test_id: [] for test_id in MCP_E2E_TEST_IDS}
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 6:
            continue
        test_id = cells[1].strip()
        if test_id in row_indexes:
            row_indexes[test_id].append(index)

    invalid_rows = [
        test_id for test_id, indexes in row_indexes.items() if len(indexes) != 1
    ]
    if invalid_rows:
        raise ValueError(
            "Expected exactly one report row for every MCP E2E test ID; "
            "invalid rows: " + ", ".join(invalid_rows)
        )

    for test_id, status in statuses.items():
        if test_id not in row_indexes:
            raise ValueError(f"Unknown MCP E2E test ID: {test_id}")
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status for {test_id}: {status!r}")
        row_index = row_indexes[test_id][0]
        cells = lines[row_index].split("|")
        cells[4] = f" {STATUS_ICONS[status]} {status} "
        lines[row_index] = "|".join(cells)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=report_path.parent,
            prefix=".mcp-report-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            temporary.write("\n".join(lines) + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_path, report_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()

    print(f"Updated MCP E2E statuses in {report_path}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    reports = getattr(item, "_mcp_e2e_reports", [])
    reports.append(report)
    setattr(item, "_mcp_e2e_reports", reports)


def pytest_sessionfinish(session, exitstatus):
    del exitstatus
    collected_by_group: dict[str, set[str]] = {
        group: set() for group in MCP_TEST_ID_GROUPS
    }
    reports_by_id: dict[str, list[pytest.TestReport]] = {
        test_id: [] for test_id in MCP_E2E_TEST_IDS
    }

    for item in session.items:
        test_id = _test_id(item.nodeid)
        if test_id is None:
            continue
        group = test_id.split("-")[1]
        collected_by_group[group].add(test_id)
        reports_by_id[test_id].extend(getattr(item, "_mcp_e2e_reports", []))

    active_groups = {
        group for group, ids in collected_by_group.items() if ids
    }
    if not active_groups:
        return

    # When a family is selected, reset its uncollected cases to "Not implemented"
    # so a partial run cannot leave stale green statuses in the report.
    ids_to_update = {
        test_id
        for group in active_groups
        for test_id in MCP_TEST_ID_GROUPS[group]
    }
    statuses = {
        test_id: _status_for_reports(reports_by_id[test_id])
        for test_id in ids_to_update
    }
    try:
        _update_mcp_report(statuses)
    except (OSError, ValueError) as exc:
        print(f"ERROR: Unable to update MCP E2E report: {exc}", file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@dataclass(frozen=True)
class MCPSettings:
    url: str
    host_header: str


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: Any
    body: bytes


def _settings() -> MCPSettings:
    if os.environ.get("RUN_MCP_INTEGRATION") != "1":
        pytest.skip(
            "BLOCKED: set RUN_MCP_INTEGRATION=1 only when the intended "
            "MCP test server is running and reachable."
        )
    return MCPSettings(
        url=os.environ.get("MCP_INTEGRATION_URL", "http://127.0.0.1:8000/mcp"),
        host_header=os.environ.get("MCP_INTEGRATION_HOST", "mcp-server:8000"),
    )


class MCPTransportClient:
    def __init__(self, settings: MCPSettings) -> None:
        self.settings = settings

    def run(self, operation: Callable[[Client], Any | Awaitable[Any]]) -> Any:
        return asyncio.run(self._run(operation))

    async def _run(self, operation: Callable[[Client], Any | Awaitable[Any]]) -> Any:
        async with httpx2.AsyncClient(
            headers={
                "Host": self.settings.host_header,
                "Accept": "application/json, text/event-stream",
            },
            timeout=httpx2.Timeout(30.0, read=60.0),
        ) as http_client:
            transport = streamable_http_client(
                self.settings.url, http_client=http_client
            )
            async with Client(transport) as client:
                result = operation(client)
                if inspect.isawaitable(result):
                    return await result
                return result

    def call_tool(self, name: str) -> Any:
        async def operation(client: Client) -> Any:
            result = await client.call_tool(name)
            if result.is_error:
                raise AssertionError(
                    f"MCP tool {name!r} returned an error: {result.content!r}"
                )
            structured = result.structured_content
            if structured is not None:
                value = (
                    structured["result"]
                    if isinstance(structured, dict) and set(structured) == {"result"}
                    else structured
                )
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                return value
            for content in result.content:
                text = getattr(content, "text", None)
                if text is not None:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
            return None

        return self.run(operation)


@pytest.fixture
def mcp_settings() -> MCPSettings:
    return _settings()


@pytest.fixture
def mcp_client(mcp_settings: MCPSettings) -> MCPTransportClient:
    return MCPTransportClient(mcp_settings)


@pytest.fixture
def mcp_client_factory(mcp_settings: MCPSettings):
    return lambda: MCPTransportClient(mcp_settings)


@pytest.fixture
def raw_mcp_request(mcp_settings: MCPSettings):
    def send(
        body: bytes,
        *,
        host: str | None = None,
        origin: str | None = None,
        timeout: float = 10.0,
    ) -> HTTPResult:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Host": host or mcp_settings.host_header,
            "MCP-Protocol-Version": "2026-07-28",
        }
        # MCP 2026-07-28 mirrors the JSON-RPC method into the standard
        # Mcp-Method header. Keep malformed JSON/request tests malformed by
        # adding the header only when a string method can be read from the body.
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("method"), str):
            headers["Mcp-Method"] = payload["method"]
        if origin is not None:
            headers["Origin"] = origin
        request = Request(mcp_settings.url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                return HTTPResult(response.status, response.headers, response.read())
        except HTTPError as exc:
            return HTTPResult(exc.code, exc.headers, exc.read())

    return send
