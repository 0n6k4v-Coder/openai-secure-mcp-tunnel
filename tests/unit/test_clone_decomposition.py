from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from local_mcp_server.clone.decomposition import (
    _normalize_relative_path,
    decompose_live_proxy,
    audit_decomposition_fidelity,
)


def test_normalize_relative_path() -> None:
    assert _normalize_relative_path("apps/paypers/decomposition") == "apps/paypers/decomposition"
    assert _normalize_relative_path("src/components") == "src/components"

    with pytest.raises(ValueError):
        _normalize_relative_path("/absolute/path")

    with pytest.raises(ValueError):
        _normalize_relative_path("path/with/../traversal")

    with pytest.raises(ValueError):
        _normalize_relative_path("")


@patch("local_mcp_server.clone.decomposition.execute_sandbox_argv")
def test_decompose_live_proxy_success(mock_execute: MagicMock) -> None:
    mock_execute.side_effect = [
        # 1. check_source
        {"return_code": 0},
        # 2. mkdir
        {"return_code": 0},
        # 3. sync assets
        {"return_code": 0},
        # 4. runner
        {
            "return_code": 0,
            "stdout": json.dumps({
                "success": True,
                "componentsCount": 14,
                "components": [
                    {"name": "nav", "lines": 40, "bytes": 2000, "maxLineLength": 115},
                    {"name": "hero", "lines": 35, "bytes": 1800, "maxLineLength": 110},
                ],
                "masterPage": "src/page.html",
                "cssFile": "src/css/inline-head.css",
                "cssBytes": 14000,
                "indexHtmlBytes": 150000,
                "formatted": True,
            }),
        },
    ]

    res = decompose_live_proxy(
        "web-cloning",
        "apps/paypers/live-proxy",
        "apps/paypers/decomposition",
        format_code=True,
    )

    assert res["success"] is True
    assert res["componentsCount"] == 14
    assert res["formatted"] is True
    assert res["sandbox_name"] == "web-cloning"
    assert res["source_dir"] == "apps/paypers/live-proxy"
    assert res["output_dir"] == "apps/paypers/decomposition"


@patch("local_mcp_server.clone.decomposition.execute_sandbox_argv")
def test_decompose_live_proxy_missing_source(mock_execute: MagicMock) -> None:
    mock_execute.return_value = {"return_code": 1}

    with pytest.raises(FileNotFoundError):
        decompose_live_proxy(
            "web-cloning",
            "apps/nonexistent/live-proxy",
            "apps/nonexistent/decomposition",
        )


@patch("local_mcp_server.clone.decomposition.execute_sandbox_argv")
def test_audit_decomposition_fidelity_passed(mock_execute: MagicMock) -> None:
    mock_execute.return_value = {
        "return_code": 0,
        "stdout": json.dumps({
            "passed": True,
            "score": 1.0,
            "checks": {"requiredFiles": True, "componentsCount": 15},
            "formatting": {
                "totalComponents": 15,
                "totalLines": 1200,
                "maxLineLengthObserved": 120,
                "unformattedComponents": [],
                "isBalanced": True,
            },
            "assets": {
                "phoneFrameExists": True,
                "phoneIslandExists": True,
            },
            "domParity": {
                "sectionsMatch": True,
                "navsMatch": True,
            },
            "warnings": [],
            "errors": [],
        }),
    }

    res = audit_decomposition_fidelity(
        "web-cloning",
        "apps/paypers/live-proxy",
        "apps/paypers/decomposition",
    )

    assert res["passed"] is True
    assert res["score"] == 1.0
    assert res["formatting"]["isBalanced"] is True
    assert res["assets"]["phoneFrameExists"] is True
