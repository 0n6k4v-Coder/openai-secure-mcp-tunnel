from __future__ import annotations

import argparse
import importlib
import json

import argcomplete
import pytest
from argcomplete.completers import EnvironCompleter


completion = importlib.import_module("local_mcp_server.cli.completion")


def test_build_mcpctl_completion_parser_contains_unified_commands() -> None:
    parser = completion._build_mcpctl_completion_parser()

    assert parser.prog == "mcpctl"
    commands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    assert {
        "start",
        "stop",
        "restart",
        "compose-status",
        "logs",
        "setup",
        "status",
        "repair",
        "sandbox",
        "credential",
        "workspace",
        "config",
    }.issubset(commands.choices)


def test_sandbox_name_completer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        completion,
        "list_sandboxes",
        lambda: json.dumps([{"name": "api"}, {"name": "browser"}, {"name": "worker"}]),
    )

    assert completion._sandbox_name_completer(prefix="br") == ["browser"]


def test_sandbox_name_completer_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completion, "list_sandboxes", lambda: "invalid-json")

    assert completion._sandbox_name_completer(prefix="") == []


def test_workspace_id_completer(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_workspace_id_completer_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error() -> list[dict[str, object]]:
        raise RuntimeError("workspace registry unavailable")

    monkeypatch.setattr(completion, "_list_grants", raise_error)

    assert completion._workspace_id_completer(prefix="") == []


def test_dynamic_completers_are_attached() -> None:
    parser = completion._build_mcpctl_completion_parser()
    parsers = {
        current_parser.prog: current_parser
        for current_parser in completion._iter_parsers(parser)
    }

    sandbox_status = parsers["mcpctl sandbox status"]
    sandbox_create = parsers["mcpctl sandbox create"]
    credential_create = parsers["mcpctl credential create"]

    sandbox_name_action = next(
        action for action in sandbox_status._actions if action.dest == "name"
    )
    assert sandbox_name_action.completer is completion._sandbox_name_completer

    workspace_action = next(
        action for action in sandbox_create._actions if action.dest == "workspace_id"
    )
    assert workspace_action.completer is completion._workspace_id_completer

    credential_key_action = next(
        action for action in credential_create._actions
        if "--key" in action.option_strings
    )
    assert credential_key_action.completer is EnvironCompleter


def test_mcpctl_shellcode_targets_mcpctl() -> None:
    shellcode = argcomplete.shellcode(["mcpctl"], shell="bash")

    assert "mcpctl" in shellcode


def test_mcpctl_main_delegates_to_cli(
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
        "_mcpctl_main",
        lambda argv=None: captured.update({"argv": argv}) or 17,
    )

    assert completion.mcpctl_main(["--help"]) == 17
    assert captured["argv"] == ["--help"]
    assert isinstance(captured["parser"], argparse.ArgumentParser)
