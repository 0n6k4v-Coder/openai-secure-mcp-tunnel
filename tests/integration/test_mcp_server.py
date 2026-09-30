from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest


@pytest.mark.integration
def test_mcp_health_endpoint() -> None:
    if os.environ.get(
        "RUN_MCP_INTEGRATION"
    ) != "1":
        pytest.skip(
            "Set RUN_MCP_INTEGRATION=1 to run MCP integration tests."
        )

    request = urllib.request.Request(
        "http://127.0.0.1:8000/healthz",
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=5,
        ) as response:
            body = response.read().decode(
                "utf-8"
            )

    except urllib.error.URLError as exc:
        pytest.fail(
            f"MCP health endpoint is unreachable: {exc}"
        )

    assert response.status == 200
    assert '"status":"ok"' in body