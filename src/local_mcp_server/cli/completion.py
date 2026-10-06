# PYTHON_ARGCOMPLETE_OK

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable

import argcomplete
from argcomplete.completers import EnvironCompleter

from ..sandbox.service import list_sandboxes
from .mcpctl import _build_parser as _build_mcpctl_parser
from .mcpctl import main as _mcpctl_main
from .workspace_broker import _list_grants
from ..runtime.registry import list_runtimes


def _filter_prefix(values: Iterable[str], prefix: str) -> list[str]:
    return sorted(
        {
            value
            for value in values
            if isinstance(value, str) and value.startswith(prefix)
        }
    )


def _sandbox_name_completer(*, prefix: str, **_: object) -> list[str]:
    try:
        data = json.loads(list_sandboxes())
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    names: list[str] = []

    for record in data:
        if not isinstance(record, dict):
            continue

        name = record.get("name")
        if isinstance(name, str) and name:
            names.append(name)

    return _filter_prefix(names, prefix)


def _workspace_id_completer(*, prefix: str, **_: object) -> list[str]:
    try:
        grants = _list_grants(verbose=True)
    except Exception:
        return []

    workspace_ids: list[str] = []

    for grant in grants:
        workspace_id = grant.get("workspace_id")
        if isinstance(workspace_id, str) and workspace_id:
            workspace_ids.append(workspace_id)

    return _filter_prefix(workspace_ids, prefix)


def _iter_parsers(
    parser: argparse.ArgumentParser,
) -> Iterable[argparse.ArgumentParser]:
    yield parser

    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue

        seen: set[int] = set()

        for child in action.choices.values():
            identity = id(child)
            if identity in seen:
                continue

            seen.add(identity)
            yield from _iter_parsers(child)


def _configure_dynamic_completers(
    parser: argparse.ArgumentParser,
) -> None:
    for current_parser in _iter_parsers(parser):
        parser_path = current_parser.prog.split()
        for action in current_parser._actions:
            if action.dest == "name" and "runtime" in parser_path:
                action.completer = lambda **_: [profile.name for profile in list_runtimes()]

        for action in current_parser._actions:
            if action.dest == "workspace_id":
                action.completer = _workspace_id_completer
                continue

            if action.dest == "name" and "sandbox" in parser_path:
                action.completer = _sandbox_name_completer
                continue

            if action.dest == "sandbox_name":
                action.completer = _sandbox_name_completer


def _configure_environment_completers(
    parser: argparse.ArgumentParser,
) -> None:
    for current_parser in _iter_parsers(parser):
        for action in current_parser._actions:
            if "--key" in action.option_strings:
                action.completer = EnvironCompleter


def _build_mcpctl_completion_parser() -> argparse.ArgumentParser:
    parser = _build_mcpctl_parser()
    _configure_dynamic_completers(parser)
    _configure_environment_completers(parser)
    return parser


def mcpctl_main(argv: list[str] | None = None) -> int:
    parser = _build_mcpctl_completion_parser()
    argcomplete.autocomplete(parser)
    return _mcpctl_main(argv)


if __name__ == "__main__":
    raise SystemExit(mcpctl_main())
