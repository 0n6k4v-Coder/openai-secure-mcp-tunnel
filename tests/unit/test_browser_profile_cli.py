from __future__ import annotations

import importlib

import pytest


cli = importlib.import_module("local_mcp_server.cli.main")


def test_sandbox_create_accepts_browser_profile() -> None:
    parser = cli._build_parser()

    args = parser.parse_args(
        [
            "sandbox",
            "create",
            "browser-one",
            "--workspace",
            "ws_project",
            "--profile",
            "browser",
        ]
    )

    assert args.command == "sandbox"
    assert args.sandbox_command == "create"
    assert args.profile == "browser"


def test_sandbox_create_rejects_name_longer_than_gateway_limit() -> None:
    policy = importlib.import_module("local_mcp_server.sandbox.policy")

    with pytest.raises(ValueError, match="at most 19 characters"):
        cli._sandbox_create(
            "a" * (policy.MAX_SANDBOX_NAME_LENGTH + 1),
            "ws_project",
            False,
            False,
            "browser",
        )
