from __future__ import annotations

import asyncio
import importlib
import json

import pytest

from mcp.server import MCPServer

from local_mcp_server.sandbox.tools import register_tools


cli = importlib.import_module("local_mcp_server.cli.main")
mcpctl = importlib.import_module("local_mcp_server.cli.mcpctl")
sandbox = importlib.import_module(
    "local_mcp_server.infrastructure.openshell.sandbox",
)
sandbox_service = importlib.import_module(
    "local_mcp_server.sandbox.service",
)


def test_main_parser_contains_extended_sandbox_lifecycle_commands() -> None:
    parser = cli._build_parser()

    args = parser.parse_args(
        ["sandbox", "restart", "project-api"],
    )

    assert args.command == "sandbox"
    assert args.sandbox_command == "restart"
    assert callable(args.handler)

    args = parser.parse_args(
        ["sandbox", "repair", "project-api"],
    )

    assert args.sandbox_command == "repair"
    assert callable(args.handler)

    args = parser.parse_args(
        ["sandbox", "recreate", "project-api", "--yes"],
    )

    assert args.sandbox_command == "recreate"
    assert args.confirmed is True
    assert callable(args.handler)


def test_mcpctl_parser_contains_extended_sandbox_lifecycle_commands() -> None:
    parser = mcpctl._build_parser()

    for command in ("restart", "repair"):
        args = parser.parse_args(
            ["sandbox", command, "project-api"],
        )

        assert args.command == "sandbox"
        assert args.sandbox_command == command

    args = parser.parse_args(
        ["sandbox", "recreate", "project-api", "--yes"],
    )

    assert args.command == "sandbox"
    assert args.sandbox_command == "recreate"
    assert args.confirmed is True


def test_recreate_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "recreate_sandbox",
        lambda name: json.dumps({"name": name}),
    )

    with pytest.raises(
        ValueError,
        match=r"sandbox recreate requires --yes",
    ):
        cli._sandbox_recreate(
            "project-api",
            False,
        )


def test_restart_stops_then_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        cli,
        "_sandbox_stop",
        lambda name: calls.append(f"stop:{name}") or cli.EXIT_OK,
    )

    monkeypatch.setattr(
        cli,
        "_sandbox_start",
        lambda name: calls.append(f"start:{name}") or cli.EXIT_OK,
    )

    assert cli._sandbox_restart("project-api") == cli.EXIT_OK

    assert calls == [
        "stop:project-api",
        "start:project-api",
    ]


def test_restart_does_not_start_after_stop_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        cli,
        "_sandbox_stop",
        lambda name: calls.append(f"stop:{name}") or 17,
    )

    monkeypatch.setattr(
        cli,
        "_sandbox_start",
        lambda name: calls.append(f"start:{name}") or cli.EXIT_OK,
    )

    assert cli._sandbox_restart("project-api") == 17

    assert calls == [
        "stop:project-api",
    ]


def test_repair_invokes_open_shell_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_command_exists", lambda command: None)
    captured: dict[str, object] = {}

    fake_completed = cli.subprocess.CompletedProcess(
        args=["openshell", "sandbox", "start", "project-api"],
        returncode=0,
        stdout="started\n",
        stderr="",
    )

    def fake_capture(command, *, cwd=cli.PROJECT_ROOT, env=None):
        captured["command"] = command
        return fake_completed

    monkeypatch.setattr(cli, "_run_capture", fake_capture)

    assert cli._sandbox_repair("project-api") == cli.EXIT_OK
    assert captured["command"] == ["openshell", "sandbox", "start", "project-api"]


def test_sandbox_repair_unresumable_supervisor_failure_reports_guidance(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_command_exists", lambda command: None)
    fake_completed = cli.subprocess.CompletedProcess(
        args=["openshell", "sandbox", "start", "crashed-sbx"],
        returncode=1,
        stdout="",
        stderr=(
            "Error:   × code: 'The system is not in a state required for the operation\'s\n"
            "  │ execution', message: \"sandbox must be Stopped, Completed, or a failed\n"
            "  │ main-process Error to start (current phase: Error)\"\n"
        ),
    )
    monkeypatch.setattr(cli, "_run_capture", lambda *args, **kwargs: fake_completed)

    result = cli._sandbox_repair("crashed-sbx")

    assert result == cli.EXIT_ERROR
    captured = capsys.readouterr()
    assert "ERROR: Sandbox 'crashed-sbx' is in an unrecoverable Error phase and cannot be repaired directly." in captured.err
    assert "Reason: The sandbox container or supervisor terminated unexpectedly" in captured.err
    assert "mcpctl sandbox recreate --yes crashed-sbx" in captured.err


def test_sandbox_start_unresumable_supervisor_failure_reports_guidance(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_command_exists", lambda command: None)
    fake_completed = cli.subprocess.CompletedProcess(
        args=["openshell", "sandbox", "start", "crashed-sbx"],
        returncode=1,
        stdout="",
        stderr="Error:   × message: \"sandbox must be Stopped, Completed, or a failed main-process Error to start (current phase: Error)\"",
    )
    monkeypatch.setattr(cli, "_run_capture", lambda *args, **kwargs: fake_completed)

    result = cli._sandbox_start("crashed-sbx")

    assert result == cli.EXIT_ERROR
    captured = capsys.readouterr()
    assert "ERROR: Sandbox 'crashed-sbx' is in an unrecoverable Error phase and cannot be started directly." in captured.err
    assert "mcpctl sandbox recreate --yes crashed-sbx" in captured.err


def test_sandbox_restart_unresumable_supervisor_failure_reports_guidance(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_command_exists", lambda command: None)
    fake_completed = cli.subprocess.CompletedProcess(
        args=["openshell", "sandbox", "stop", "crashed-sbx"],
        returncode=1,
        stdout="",
        stderr="Error:   × message: \"sandbox must be Ready to stop (current phase: Error)\"",
    )
    monkeypatch.setattr(cli, "_run_capture", lambda *args, **kwargs: fake_completed)

    result = cli._sandbox_restart("crashed-sbx")

    assert result == cli.EXIT_ERROR
    captured = capsys.readouterr()
    assert "ERROR: Sandbox 'crashed-sbx' is in an unrecoverable Error phase and cannot be stopped directly." in captured.err
    assert "mcpctl sandbox recreate --yes crashed-sbx" in captured.err


def test_sandbox_repair_generic_failure_propagates_raw_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_command_exists", lambda command: None)
    fake_completed = cli.subprocess.CompletedProcess(
        args=["openshell", "sandbox", "start", "generic-sbx"],
        returncode=1,
        stdout="",
        stderr="Error: connection refused\n",
    )
    monkeypatch.setattr(cli, "_run_capture", lambda *args, **kwargs: fake_completed)

    result = cli._sandbox_repair("generic-sbx")

    assert result == 1
    captured = capsys.readouterr()
    assert "Error: connection refused" in captured.err


def test_service_restart_stops_then_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        sandbox,
        "stop_sandbox",
        lambda name: calls.append(f"stop:{name}") or "stopped",
    )

    monkeypatch.setattr(
        sandbox,
        "start_sandbox",
        lambda name: calls.append(f"start:{name}") or "started",
    )

    assert sandbox_service.restart_sandbox("project-api") == "started"

    assert calls == [
        "stop:project-api",
        "start:project-api",
    ]


def test_service_repair_reuses_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        sandbox,
        "start_sandbox",
        lambda name: calls.append(name) or "started",
    )

    assert sandbox_service.repair_sandbox("project-api") == "started"

    assert calls == ["project-api"]


def test_browser_status_reports_devtools_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox,
        "execute_sandbox_argv",
        lambda name, argv, *, timeout_seconds: {
            "stdout": "chrome-devtools-mcp daemon is running.\n"
            "pid=123 socket=/tmp/chrome-devtools-mcp-10001.sock",
            "stderr": "",
            "return_code": 0,
        },
    )
    assert sandbox._browser_devtools_readiness("browser-1") == {
        "state": "ready",
        "detail": "chrome-devtools-mcp daemon is running.\n"
        "pid=123 socket=/tmp/chrome-devtools-mcp-10001.sock",
    }


def test_browser_status_reports_not_ready_devtools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox,
        "execute_sandbox_argv",
        lambda name, argv, *, timeout_seconds: {
            "stdout": "chrome-devtools-mcp daemon is not running.",
            "stderr": "",
            "return_code": 0,
        },
    )
    assert sandbox._browser_devtools_readiness("browser-1") == {
        "state": "not_ready",
        "detail": "chrome-devtools-mcp daemon is not running.",
    }


def test_recreate_preserves_workspace_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        sandbox,
        "sandbox_status",
        lambda name: json.dumps(
            {
                "name": name,
                "profile": "browser",
                "host_workspace_id": "ws_project",
            }
        ),
    )

    monkeypatch.setattr(
        sandbox,
        "delete_sandbox",
        lambda name: (
            calls.append(("delete", name)),
            json.dumps(
                {
                    "name": name,
                    "deleted": True,
                }
            )[1],
        )[1],
    )

    monkeypatch.setattr(
        sandbox,
        "create_sandbox",
        lambda *, name, workspace_id, profile: (
            calls.append(
                (
                    "create",
                    {
                        "name": name,
                        "workspace_id": workspace_id,
                        "profile": profile,
                    },
                )
            ),
            json.dumps(
                {
                    "name": name,
                    "profile": profile,
                    "host_workspace_id": workspace_id,
                }
            ),
        )[1],
    )

    result = sandbox.recreate_sandbox("project-api")
    data = json.loads(result)

    assert data == {
        "name": "project-api",
        "profile": "browser",
        "host_workspace_id": "ws_project",
    }

    assert calls == [
        ("delete", "project-api"),
        (
            "create",
            {
                "name": "project-api",
                "workspace_id": "ws_project",
                "profile": "browser",
            },
        ),
    ]


def test_recreate_preserves_standalone_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        sandbox,
        "sandbox_status",
        lambda name: json.dumps(
            {
                "name": name,
                "profile": "default",
            }
        ),
    )
    monkeypatch.setattr(
        sandbox,
        "delete_sandbox",
        lambda name: calls.append(("delete", name)) or json.dumps({"name": name}),
    )
    monkeypatch.setattr(
        sandbox,
        "create_sandbox",
        lambda name, workspace_id=None, profile="default": calls.append(
            (
                "create",
                {
                    "name": name,
                    "workspace_id": workspace_id,
                    "profile": profile,
                },
            )
        )
        or json.dumps(
            {
                "name": name,
                "profile": profile,
                "host_workspace_id": workspace_id,
            }
        ),
    )

    result = sandbox.recreate_sandbox("project-api")
    data = json.loads(result)

    assert data == {
        "name": "project-api",
        "profile": "default",
        "host_workspace_id": None,
    }

    assert calls == [
        ("delete", "project-api"),
        (
            "create",
            {
                "name": "project-api",
                "workspace_id": None,
                "profile": "default",
            },
        ),
    ]


def test_recreate_rejects_unsupported_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox,
        "sandbox_status",
        lambda name: json.dumps(
            {
                "name": name,
                "profile": "unknown",
                "host_workspace_id": "ws_project",
            }
        ),
    )

    with pytest.raises(
        sandbox.SandboxError,
        match="unsupported profile",
    ):
        sandbox.recreate_sandbox("project-api")


def test_mcp_registers_complete_sandbox_lifecycle_surface() -> None:
    mcp = MCPServer("sandbox-test")

    register_tools(mcp)

    tools = asyncio.run(mcp.list_tools())
    tool_map = {tool.name: tool for tool in tools}

    expected = {
        "get_system_info",
        "create_sandbox",
        "list_sandboxes",
        "sandbox_status",
        "sandbox_logs",
        "start_sandbox",
        "stop_sandbox",
        "restart_sandbox",
        "repair_sandbox",
        "recreate_sandbox",
        "delete_sandbox",
        "execute_sandbox_command",
    }

    assert expected <= set(tool_map)

    assert tool_map["sandbox_logs"].annotations.read_only_hint is True
    assert tool_map["sandbox_logs"].annotations.idempotent_hint is True

    assert tool_map["repair_sandbox"].annotations.destructive_hint is False
    assert tool_map["repair_sandbox"].annotations.idempotent_hint is True

    assert tool_map["restart_sandbox"].annotations.destructive_hint is True
    assert tool_map["restart_sandbox"].annotations.idempotent_hint is False

    assert tool_map["recreate_sandbox"].annotations.destructive_hint is True
    assert tool_map["recreate_sandbox"].annotations.idempotent_hint is False
