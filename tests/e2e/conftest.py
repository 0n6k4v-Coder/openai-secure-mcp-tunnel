from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


CLI_MCP_TEST_IDS = tuple(f"CLI-MCP-{number:03d}" for number in range(1, 13))
CLI_SBX_CREATE_TEST_IDS = tuple(
    f"CLI-SBX-{number:03d}" for number in range(1, 17)
)
CLI_E2E_TEST_IDS = CLI_MCP_TEST_IDS + CLI_SBX_CREATE_TEST_IDS

VALID_STATUSES = {"Not implemented", "Blocked", "Pass", "Fail", "Skipped"}
STATUS_ICONS = {
    "Not implemented": "⚪",
    "Blocked": "🟠",
    "Pass": "🟢",
    "Fail": "🔴",
    "Skipped": "🟡",
}
TEST_ID_PATTERN = re.compile(
    r"CLI[-_](MCP|SBX)[-_](\d{3})",
    re.IGNORECASE,
)


def _test_id(node_id: str) -> str | None:
    match = TEST_ID_PATTERN.search(node_id)
    if match is None:
        return None

    return f"CLI-{match.group(1).upper()}-{match.group(2)}"


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


def _update_cli_report(statuses: dict[str, str]) -> None:
    report_path = Path(__file__).resolve().parent / "reports" / "cli.md"
    if not report_path.is_file():
        raise FileNotFoundError(
            f"CLI E2E report does not exist: {report_path}"
        )

    lines = report_path.read_text(encoding="utf-8").splitlines()
    row_indexes: dict[str, list[int]] = {
        test_id: [] for test_id in CLI_E2E_TEST_IDS
    }

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
        test_id
        for test_id, indexes in row_indexes.items()
        if len(indexes) != 1
    ]
    if invalid_rows:
        raise ValueError(
            "Expected exactly one report row for each CLI E2E test ID; "
            "invalid rows: " + ", ".join(invalid_rows)
        )

    for test_id in CLI_E2E_TEST_IDS:
        # A filtered pytest run must not erase results for tests it did not run.
        if test_id not in statuses:
            continue

        status = statuses[test_id]
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status for {test_id}: {status!r}"
            )

        row_index = row_indexes[test_id][0]
        cells = lines[row_index].split("|")
        cells[4] = f" {STATUS_ICONS[status]} {status} "
        lines[row_index] = "|".join(cells)

    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(f"Updated CLI E2E statuses in {report_path}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    reports = getattr(item, "_cli_e2e_reports", [])
    reports.append(report)
    setattr(item, "_cli_e2e_reports", reports)


def pytest_sessionfinish(session, exitstatus):
    del exitstatus

    cli_items = [
        item
        for item in session.items
        if _test_id(item.nodeid) in CLI_E2E_TEST_IDS
    ]
    if not cli_items:
        return

    reports_by_id: dict[str, list[pytest.TestReport]] = {
        test_id: [] for test_id in CLI_E2E_TEST_IDS
    }

    for item in cli_items:
        test_id = _test_id(item.nodeid)
        if test_id is not None:
            reports_by_id[test_id].extend(
                getattr(item, "_cli_e2e_reports", [])
            )

    collected_ids = {
        _test_id(item.nodeid) for item in cli_items
    }
    full_suite_collected = (
        len(cli_items) == len(CLI_E2E_TEST_IDS)
        and collected_ids == set(CLI_E2E_TEST_IDS)
    )

    statuses = {
        test_id: _status_for_reports(reports_by_id[test_id])
        for test_id in CLI_E2E_TEST_IDS
        if full_suite_collected or test_id in collected_ids
    }

    try:
        _update_cli_report(statuses)
    except (OSError, ValueError) as exc:
        print(
            f"ERROR: Unable to update CLI E2E report: {exc}",
            file=sys.stderr,
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
