from __future__ import annotations

import importlib


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
