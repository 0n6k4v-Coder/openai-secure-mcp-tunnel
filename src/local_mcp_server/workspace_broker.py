from __future__ import annotations

import argparse
import json
import sys

from .workspace import (
    create_workspace_grant,
    list_workspace_grants,
    revoke_workspace_grant,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-broker",
        description=(
            "Host-only workspace authorization broker. "
            "Run this command on the host, never as an MCP tool."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    authorize = subparsers.add_parser(
        "authorize",
        help="Authorize one host directory for sandbox use.",
    )
    authorize.add_argument(
        "host_path",
        help="Absolute host directory selected by the human operator.",
    )

    revoke = subparsers.add_parser(
        "revoke",
        help="Revoke an authorized workspace capability.",
    )
    revoke.add_argument(
        "workspace_id",
        help="Opaque capability ID (e.g. ws_...) to revoke.",
    )

    subparsers.add_parser(
        "list",
        help="List currently authorized workspace capabilities.",
    )

    return parser


def _authorize(host_path: str) -> int:
    grant = create_workspace_grant(host_path)

    print(
        json.dumps(
            grant,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def _revoke(workspace_id: str) -> int:
    result = revoke_workspace_grant(workspace_id)

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def _list() -> int:
    print(
        json.dumps(
            list_workspace_grants(),
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "authorize":
            return _authorize(args.host_path)

        if args.command == "revoke":
            return _revoke(args.workspace_id)

        if args.command == "list":
            return _list()

        parser.error(f"unsupported command: {args.command}")

    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
