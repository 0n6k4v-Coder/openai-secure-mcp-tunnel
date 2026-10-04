from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest


TEST_IDS_BY_FILE = {
    "test_create_list.py": tuple(f"MCP-SBX-{number:03d}" for number in range(1, 14)),
    "test_status_logs.py": tuple(f"MCP-SBX-{number:03d}" for number in range(20, 28)),
    "test_lifecycle.py": tuple(f"MCP-SBX-{number:03d}" for number in range(30, 47)),
    "test_execute_commands.py": tuple(
        f"MCP-SBX-{number:03d}" for number in range(50, 58)
    ),
}
ALL_TEST_IDS = tuple(
    test_id for test_ids in TEST_IDS_BY_FILE.values() for test_id in test_ids
)
VALID_STATUSES = {"Not implemented", "Blocked", "Pass", "Fail", "Skipped"}
STATUS_ICONS = {
    "Not implemented": "⚪",
    "Blocked": "🟠",
    "Pass": "🟢",
    "Fail": "🔴",
    "Skipped": "🟡",
}
TEST_ID_PATTERN = re.compile(r"MCP[-_]SBX[-_](\d{3})")


def _test_id(node_id: str) -> str | None:
    match = TEST_ID_PATTERN.search(node_id)
    if match is None:
        return None
    test_id = f"MCP-SBX-{match.group(1)}"
    return test_id if test_id in ALL_TEST_IDS else None


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


def _update_report(statuses: dict[str, str]) -> None:
    report_path = Path(__file__).resolve().parents[2] / "reports" / "mcp.md"
    original_mode = stat.S_IMODE(report_path.stat().st_mode)
    lines = report_path.read_text(encoding="utf-8").splitlines()
    row_indexes: dict[str, list[int]] = {test_id: [] for test_id in ALL_TEST_IDS}

    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 6:
            continue
        test_id = cells[1].strip()
        if test_id in row_indexes:
            row_indexes[test_id].append(index)

    invalid = [test_id for test_id, indexes in row_indexes.items() if len(indexes) != 1]
    if invalid:
        raise ValueError(
            "Expected exactly one report row for every MCP-SBX test ID; "
            "invalid rows: " + ", ".join(invalid)
        )

    for test_id, status in statuses.items():
        if test_id not in row_indexes or status not in VALID_STATUSES:
            raise ValueError(f"Invalid report update: {test_id}={status!r}")
        row_index = row_indexes[test_id][0]
        cells = lines[row_index].split("|")
        cells[4] = f" {STATUS_ICONS[status]} {status} "
        lines[row_index] = "|".join(cells)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=report_path.parent,
            prefix=".mcp-sbx-report-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write("\n".join(lines) + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, report_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    print(f"Updated MCP-SBX E2E statuses in {report_path}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    reports = getattr(item, "_mcp_sbx_reports", [])
    reports.append(report)
    setattr(item, "_mcp_sbx_reports", reports)


def pytest_sessionfinish(session, exitstatus):
    del exitstatus
    reports_by_id: dict[str, list[pytest.TestReport]] = {
        test_id: [] for test_id in ALL_TEST_IDS
    }
    active_files: set[str] = set()

    for item in session.items:
        test_id = _test_id(item.nodeid)
        if test_id is None:
            continue
        active_files.add(Path(str(item.path)).name)
        reports_by_id[test_id].extend(getattr(item, "_mcp_sbx_reports", []))

    if not active_files:
        return

    # A file-by-file run updates only its own test family and preserves results
    # already recorded by other files.
    ids_to_update = {
        test_id for filename in active_files for test_id in TEST_IDS_BY_FILE[filename]
    }
    statuses = {
        test_id: _status_for_reports(reports_by_id[test_id])
        for test_id in ids_to_update
    }

    try:
        _update_report(statuses)
    except (OSError, ValueError) as exc:
        print(f"ERROR: Unable to update MCP-SBX report: {exc}", file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def require_disposable_mcp_sandbox_environment() -> None:
    required = {
        "RUN_MCP_INTEGRATION": "1",
        "MCP_SBX_E2E_ISOLATED": "1",
        "MCP_SBX_E2E_ALLOW_MUTATIONS": "1",
        "MCP_SBX_E2E_CONFIRM_DISPOSABLE": "YES",
    }
    for variable, expected in required.items():
        if os.environ.get(variable) != expected:
            pytest.skip(
                f"BLOCKED: set {variable}={expected} only after verifying "
                "the intended MCP endpoint and disposable OpenShell environment."
            )


def _invoke(mcp_client: Any, tool_name: str, arguments: dict[str, Any] | None = None):
    return mcp_client.run(lambda client: client.call_tool(tool_name, arguments or {}))


def _result_text(result: Any) -> str:
    return "\n".join(
        block.text
        for block in result.content
        if isinstance(getattr(block, "text", None), str)
    )


def _decode_result(result: Any) -> Any:
    value = getattr(result, "structured_content", None)
    if value is not None:
        if isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    raw = _result_text(result)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _call_ok(
    mcp_client: Any,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    result = _invoke(mcp_client, tool_name, arguments)
    assert not result.is_error, (
        f"MCP tool {tool_name!r} returned an error: {_result_text(result)!r}"
    )
    return _decode_result(result)


def _call_error(
    mcp_client: Any,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> str:
    result = _invoke(mcp_client, tool_name, arguments)
    assert result.is_error, (
        f"MCP tool {tool_name!r} should have failed but returned "
        f"{_decode_result(result)!r}"
    )
    return _result_text(result)


def _new_sandbox_name() -> str:
    return f"e2e-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def sandbox_factory(mcp_client: Any, request: pytest.FixtureRequest):
    created_names: list[str] = []

    def create(
        name: str | None = None,
        *,
        profile: str = "default",
        host_workspace_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        sandbox_name = name or _new_sandbox_name()
        arguments: dict[str, Any] = {"name": sandbox_name, "profile": profile}
        if host_workspace_id is not None:
            arguments["host_workspace_id"] = host_workspace_id
        if sandbox_name not in created_names:
            created_names.append(sandbox_name)
        value = _call_ok(mcp_client, "create_sandbox", arguments)
        assert isinstance(value, dict), f"Expected JSON object, got {value!r}"
        assert value.get("name") == sandbox_name, value
        return sandbox_name, value

    def cleanup() -> None:
        for sandbox_name in reversed(created_names):
            status_result = _invoke(
                mcp_client, "sandbox_status", {"name": sandbox_name}
            )
            if status_result.is_error:
                if "not found" in _result_text(status_result).lower():
                    continue
            delete_result = _invoke(
                mcp_client, "delete_sandbox", {"name": sandbox_name}
            )
            if delete_result.is_error:
                pytest.fail(
                    f"Cleanup failed for {sandbox_name}: {_result_text(delete_result)}"
                )
            verify_result = _invoke(
                mcp_client, "sandbox_status", {"name": sandbox_name}
            )
            if not verify_result.is_error:
                pytest.fail(f"Sandbox {sandbox_name} remains after cleanup.")

    request.addfinalizer(cleanup)
    return create


@pytest.fixture
def created_sandbox(sandbox_factory):
    return sandbox_factory()


@pytest.fixture
def missing_sandbox_name() -> str:
    return f"e2e-missing-{uuid.uuid4().hex[:6]}"


@pytest.fixture
def host_workspace_id() -> str:
    value = os.environ.get("MCP_SBX_E2E_HOST_WORKSPACE_ID", "").strip()
    if not value:
        pytest.skip(
            "BLOCKED: MCP_SBX_E2E_HOST_WORKSPACE_ID must identify an authorized "
            "disposable host workspace grant."
        )
    return value


@pytest.fixture
def browser_profile_enabled() -> None:
    if os.environ.get("MCP_SBX_E2E_BROWSER_PROFILE") != "1":
        pytest.skip(
            "BLOCKED: enable MCP_SBX_E2E_BROWSER_PROFILE=1 only when the "
            "dedicated test runtime has the browser image configured."
        )


@pytest.fixture
def empty_workspace_assertion_enabled() -> None:
    if os.environ.get("MCP_SBX_E2E_EXPECT_EMPTY") != "1":
        pytest.skip(
            "BLOCKED: enable MCP_SBX_E2E_EXPECT_EMPTY=1 only when the "
            "dedicated OpenShell workspace is expected to be empty."
        )
