from __future__ import annotations

import argparse
import importlib
import json

import argcomplete
import pytest
from argcomplete.completers import EnvironCompleter


completion = importlib.import_module("local_mcp_server.cli.completion")


def test_build_completion_parser_uses_local_cli_name() -> None:
    parser = completion._build_completion_parser()

    assert parser.prog == "local-mcp-server"


def test_build_completion_parser_contains_main_commands() -> None:
    parser = completion._build_completion_parser()

    subparser_actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]

    assert len(subparser_actions) == 1

    assert {
        "start",
        "stop",
        "restart",
        "status",
        "logs",
        "sandbox",
        "credential",
    }.issubset(subparser_actions[0].choices)


def test_sandbox_name_completer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        completion,
        "list_sandboxes",
        lambda: json.dumps(
            [
                {"name": "api"},
                {"name": "browser"},
                {"name": "worker"},
            ]
        ),
    )

    assert completion._sandbox_name_completer(prefix="br") == ["browser"]


def test_sandbox_name_completer_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        completion,
        "list_sandboxes",
        lambda: "invalid-json",
    )

    assert completion._sandbox_name_completer(prefix="") == []


def test_workspace_id_completer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        completion,
        "_list_grants",
        lambda: [
            {"workspace_id": "ws_alpha"},
            {"workspace_id": "ws_beta"},
            {"workspace_id": "ws_gamma"},
        ],
    )

    assert completion._workspace_id_completer(prefix="ws_b") == ["ws_beta"]


def test_workspace_id_completer_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_error() -> list[dict[str, object]]:
        raise RuntimeError("workspace registry unavailable")

    monkeypatch.setattr(completion, "_list_grants", raise_error)

    assert completion._workspace_id_completer(prefix="") == []


def test_dynamic_completers_are_attached() -> None:
    parser = completion._build_completion_parser()

    parsers = {
        current_parser.prog: current_parser
        for current_parser in completion._iter_parsers(parser)
    }

    sandbox_status = parsers["local-mcp-server sandbox status"]
    sandbox_create = parsers["local-mcp-server sandbox create"]
    credential_create = parsers["local-mcp-server credential create"]

    sandbox_name_action = next(
        action for action in sandbox_status._actions if action.dest == "name"
    )
    assert sandbox_name_action.completer is completion._sandbox_name_completer

    workspace_action = next(
        action for action in sandbox_create._actions if action.dest == "workspace_id"
    )
    assert workspace_action.completer is completion._workspace_id_completer

    credential_key_action = next(
        action
        for action in credential_create._actions
        if "--key" in action.option_strings
    )
    assert credential_key_action.completer is EnvironCompleter


def test_existing_choices_remain_available() -> None:
    parser = completion._build_completion_parser()

    sandbox_create = next(
        current_parser
        for current_parser in completion._iter_parsers(parser)
        if current_parser.prog == "local-mcp-server sandbox create"
    )

    profile_action = next(
        action for action in sandbox_create._actions if action.dest == "profile"
    )

    assert list(profile_action.choices) == ["default", "browser"]


def test_argcomplete_shellcode_targets_local_cli() -> None:
    shellcode = argcomplete.shellcode(
        ["local-mcp-server"],
        shell="bash",
    )

    assert "local-mcp-server" in shellcode


def test_main_delegates_to_existing_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        completion.argcomplete,
        "autocomplete",
        lambda parser: captured.update({"parser": parser}),
    )

    monkeypatch.setattr(
        completion,
        "_main",
        lambda argv=None: captured.update({"argv": argv}) or 17,
    )

    assert completion.main(["status", "--json"]) == 17
    assert captured["argv"] == ["status", "--json"]
    assert isinstance(captured["parser"], argparse.ArgumentParser)


def test_build_mcpctl_completion_parser_contains_nested_commands() -> None:
    parser = completion._build_mcpctl_completion_parser()

    assert parser.prog == "mcpctl"

    parsers = {
        current_parser.prog: current_parser
        for current_parser in completion._iter_parsers(parser)
    }

    assert "mcpctl sandbox" in parsers
    assert "mcpctl sandbox create" in parsers
    assert "mcpctl credential create" in parsers
    assert "mcpctl workspace authorize" in parsers
    assert "mcpctl config" in parsers
    assert "mcpctl config mcp-client" in parsers
    assert "mcpctl config mcp-client openai" in parsers

    sandbox_create = parsers["mcpctl sandbox create"]
    workspace_action = next(
        action for action in sandbox_create._actions if action.dest == "workspace_id"
    )
    assert workspace_action.completer is completion._workspace_id_completer


def test_mcpctl_config_help_contains_mcp_client() -> None:
    parser = completion._build_mcpctl_completion_parser()
    config = next(
        current_parser
        for current_parser in completion._iter_parsers(parser)
        if current_parser.prog == "mcpctl config"
    )
    subparsers = next(
        action
        for action in config._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    assert "mcp-client" in subparsers.choices


def test_mcpctl_config_mcp_client_contains_openai() -> None:
    parser = completion._build_mcpctl_completion_parser()
    mcp_client = next(
        current_parser
        for current_parser in completion._iter_parsers(parser)
        if current_parser.prog == "mcpctl config mcp-client"
    )
    subparsers = next(
        action
        for action in mcp_client._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    assert "openai" in subparsers.choices


def test_mcpctl_shellcode_targets_mcpctl() -> None:
    shellcode = argcomplete.shellcode(
        ["mcpctl"],
        shell="bash",
    )

    assert "mcpctl" in shellcode
