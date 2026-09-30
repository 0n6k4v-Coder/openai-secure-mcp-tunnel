from __future__ import annotations

import json
import subprocess

import pytest

from local_mcp_server import cli


def test_workspace_name_uses_host_directory_name() -> None:
    assert (
        cli._workspace_name(
            {
                "workspace_id": "ws_test",
                "host_path": "/home/user/project",
            }
        )
        == "project"
    )


def test_workspace_name_falls_back_to_workspace_id() -> None:
    assert (
        cli._workspace_name(
            {
                "workspace_id": "ws_test",
            }
        )
        == "ws_test"
    )


def test_find_workspace_by_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "_workspace_records",
        lambda: [
            {
                "workspace_id": "ws_one",
                "host_path": "/tmp/project-one",
            },
            {
                "workspace_id": "ws_two",
                "host_path": "/tmp/project-two",
            },
        ],
    )

    result = cli._find_workspace(
        "ws_two"
    )

    assert result["workspace_id"] == "ws_two"


def test_find_workspace_by_directory_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "_workspace_records",
        lambda: [
            {
                "workspace_id": "ws_one",
                "host_path": "/tmp/project-one",
            }
        ],
    )

    result = cli._find_workspace(
        "project-one"
    )

    assert result["workspace_id"] == "ws_one"


def test_find_workspace_rejects_ambiguous_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "_workspace_records",
        lambda: [
            {
                "workspace_id": "ws_one",
                "host_path": "/a/project",
            },
            {
                "workspace_id": "ws_two",
                "host_path": "/b/project",
            },
        ],
    )

    with pytest.raises(
        ValueError,
        match="ambiguous",
    ):
        cli._find_workspace(
            "project"
        )


def test_find_workspace_rejects_unknown_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "_workspace_records",
        lambda: [],
    )

    with pytest.raises(
        ValueError,
        match="was not found",
    ):
        cli._find_workspace(
            "missing"
        )


def test_sandbox_list_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_sandbox_records",
        lambda: [
            {
                "id": "sandbox-id",
                "name": "project-api",
                "status": "Ready",
            }
        ],
    )

    assert cli._sandbox_list(
        True
    ) == 0

    output = json.loads(
        capsys.readouterr().out
    )

    assert output[0]["name"] == "project-api"
    assert output[0]["status"] == "Ready"


def test_sandbox_create_uses_workspace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_workspace_records",
        lambda: [
            {
                "workspace_id": "ws_project",
                "host_path": "/tmp/project",
                "volume_name": "mcp-ws-project",
                "target": "/workspace/project",
                "read_only": False,
            }
        ],
    )

    captured: dict[str, object] = {}

    def fake_create_sandbox(
        *,
        name: str,
        workspace_id: str,
    ) -> str:
        captured["name"] = name
        captured["workspace_id"] = workspace_id

        return json.dumps(
            {
                "name": name,
                "status": "Ready",
                "id": "sandbox-id",
            }
        )

    monkeypatch.setattr(
        cli,
        "create_sandbox",
        fake_create_sandbox,
    )

    assert (
        cli._sandbox_create(
            "project-api",
            "project",
            False,
        )
        == 0
    )

    assert captured == {
        "name": "project-api",
        "workspace_id": "ws_project",
    }

    output = capsys.readouterr().out

    assert "Sandbox created." in output
    assert "project-api" in output
    assert "ws_project" in output


def test_sandbox_create_requires_workspace_noninteractive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "_workspace_records",
        lambda: [
            {
                "workspace_id": "ws_project",
                "host_path": "/tmp/project",
            }
        ],
    )

    monkeypatch.setattr(
        cli.sys.stdin,
        "isatty",
        lambda: False,
    )

    with pytest.raises(
        ValueError,
        match="--workspace is required",
    ):
        cli._sandbox_create(
            "test-sandbox",
            None,
            False,
        )


def test_interactive_workspace_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants = [
        {
            "workspace_id": "ws_one",
            "host_path": "/tmp/project-one",
        },
        {
            "workspace_id": "ws_two",
            "host_path": "/tmp/project-two",
        },
    ]

    monkeypatch.setattr(
        cli.sys.stdin,
        "isatty",
        lambda: True,
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: "2",
    )

    result = cli._select_workspace_interactively(
        grants
    )

    assert result["workspace_id"] == "ws_two"


def test_interactive_workspace_selection_handles_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grants = [
        {
            "workspace_id": "ws_one",
            "host_path": "/tmp/project-one",
        }
    ]

    monkeypatch.setattr(
        cli.sys.stdin,
        "isatty",
        lambda: True,
    )

    def raise_eof(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr(
        "builtins.input",
        raise_eof,
    )

    with pytest.raises(
        ValueError,
        match="cancelled",
    ):
        cli._select_workspace_interactively(
            grants
        )


def test_sandbox_connect_uses_default_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "OPEN_SHELL_GATEWAY",
        "",
    )

    captured: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["check"] = check

        return subprocess.CompletedProcess(
            command,
            0,
        )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        fake_run,
    )

    assert cli._sandbox_connect(
        "project-api"
    ) == 0

    assert captured == {
        "command": [
            "openshell",
            "sandbox",
            "connect",
            "project-api",
        ],
        "check": False,
    }


def test_sandbox_connect_uses_configured_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "OPEN_SHELL_GATEWAY",
        "http://127.0.0.1:8080",
    )

    captured: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["check"] = check

        return subprocess.CompletedProcess(
            command,
            0,
        )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        fake_run,
    )

    assert cli._sandbox_connect(
        "project-api"
    ) == 0

    assert captured == {
        "command": [
            "openshell",
            "--gateway-endpoint",
            "http://127.0.0.1:8080",
            "sandbox",
            "connect",
            "project-api",
        ],
        "check": False,
    }


def test_sandbox_connect_reports_missing_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "OPEN_SHELL_GATEWAY",
        "",
    )

    def raise_missing_cli(
        command: list[str],
        *,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(
            "openshell"
        )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        raise_missing_cli,
    )

    with pytest.raises(
        cli.SandboxError,
        match="OpenShell CLI is not installed",
    ):
        cli._sandbox_connect(
            "project-api"
        )


@pytest.mark.parametrize(
    "argv",
    [
        ["--json", "list"],
        ["list", "--json"],
    ],
)
def test_json_flag_is_accepted_before_or_after_command(
    argv: list[str],
) -> None:
    parser = cli._build_parser()
    args = parser.parse_args(
        argv
    )

    assert args.json is True
    assert args.handler == "sandbox_list"


def test_workspace_json_flag_is_accepted_after_subcommand() -> None:
    parser = cli._build_parser()

    args = parser.parse_args(
        [
            "workspace",
            "list",
            "--json",
        ]
    )

    assert args.json is True
    assert args.handler == "workspace_list"


def test_connect_rejects_json_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.main(
            [
                "--json",
                "connect",
                "project-api",
            ]
        )
        == cli.EXIT_ERROR
    )

    assert (
        "--json is not supported"
        in capsys.readouterr().err
    )


def test_main_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            ["--help"]
        )

    assert exc_info.value.code == 0

    output = capsys.readouterr().out

    assert "mcp-sandbox" in output
    assert "workspace" in output
    assert "create" in output
    assert "list" in output