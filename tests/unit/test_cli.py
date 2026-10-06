from __future__ import annotations

import importlib
import json

import pytest


cli = importlib.import_module("local_mcp_server.cli.main")


def test_status_value_prefers_status() -> None:
    assert cli._status_value({"status": "Ready", "phase": "Running"}) == "Ready"


def test_status_value_falls_back_to_phase() -> None:
    assert cli._status_value({"phase": "Running"}) == "Running"


def test_status_value_returns_unknown_when_missing() -> None:
    assert cli._status_value({}) == "UNKNOWN"


def test_sandbox_list_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "list_sandboxes",
        lambda: json.dumps(
            [
                {
                    "id": "sandbox-id",
                    "name": "project-api",
                    "status": "Ready",
                    "host_workspace_id": "ws_project",
                }
            ]
        ),
    )

    assert cli._sandbox_list(True) == cli.EXIT_OK

    output = json.loads(capsys.readouterr().out)

    assert output == [
        {
            "id": "sandbox-id",
            "name": "project-api",
            "status": "Ready",
            "host_workspace_id": "ws_project",
        }
    ]


def test_sandbox_list_table(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "list_sandboxes",
        lambda: json.dumps(
            [
                {
                    "id": "sandbox-id",
                    "name": "project-api",
                    "status": "Ready",
                    "host_workspace_id": "ws_project",
                }
            ]
        ),
    )

    assert cli._sandbox_list(False) == cli.EXIT_OK

    output = capsys.readouterr().out

    assert "NAME" in output
    assert "STATUS" in output
    assert "HOST WORKSPACE ID" in output
    assert "ID" in output
    assert "project-api" in output
    assert "Ready" in output
    assert "ws_project" in output


def test_sandbox_create_uses_workspace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "local_mcp_server.cli.lifecycle.verify_local_images",
        lambda required_variables=None: None,
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

    monkeypatch.setattr(cli, "create_sandbox", fake_create_sandbox)

    assert (
        cli._sandbox_create(
            "project-api",
            "ws_project",
            False,
            False,
        )
        == cli.EXIT_OK
    )

    assert captured == {
        "name": "project-api",
        "workspace_id": "ws_project",
    }

    output = capsys.readouterr().out

    assert "Sandbox created." in output
    assert "project-api" in output
    assert "ws_project" in output
    assert "/workspace/project" in output


def test_sandbox_create_standalone(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "local_mcp_server.cli.lifecycle.verify_local_images",
        lambda required_variables=None: None,
    )
    captured: dict[str, object] = {}

    def fake_create_sandbox(
        *,
        name: str,
        workspace_id: str | None,
    ) -> str:
        captured["name"] = name
        captured["workspace_id"] = workspace_id

        return json.dumps(
            {
                "name": name,
                "status": "Ready",
                "profile": "default",
                "workspace": {
                    "type": "sandbox",
                    "id": name,
                    "root": "/workspace/project",
                    "read_only": False,
                },
                "id": "sandbox-id",
            }
        )

    monkeypatch.setattr(cli, "create_sandbox", fake_create_sandbox)

    assert (
        cli._sandbox_create(
            "standalone-api",
            None,
            True,
            False,
        )
        == cli.EXIT_OK
    )

    assert captured == {
        "name": "standalone-api",
        "workspace_id": None,
    }

    output = capsys.readouterr().out

    assert "Sandbox created." in output
    assert "standalone-api" in output
    assert "Application workspace: sandbox-local" in output
    assert "Host workspace ID:" not in output
    assert "/workspace/project" in output


def test_sandbox_create_rejects_missing_workspace_source() -> None:
    with pytest.raises(
        ValueError,
        match="requires either --workspace WORKSPACE_ID or --standalone",
    ):
        cli._sandbox_create(
            "project-api",
            None,
            False,
            False,
        )


def test_sandbox_create_rejects_conflicting_workspace_source() -> None:
    with pytest.raises(
        ValueError,
        match="cannot use --workspace with --standalone",
    ):
        cli._sandbox_create(
            "project-api",
            "ws_project",
            True,
            False,
        )


def test_sandbox_create_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "local_mcp_server.cli.lifecycle.verify_local_images",
        lambda required_variables=None: None,
    )
    monkeypatch.setattr(
        cli,
        "create_sandbox",
        lambda *, name, workspace_id: json.dumps(
            {
                "name": name,
                "workspace": workspace_id,
                "status": "Ready",
            }
        ),
    )

    assert (
        cli._sandbox_create(
            "project-api",
            "ws_project",
            False,
            True,
        )
        == cli.EXIT_OK
    )

    output = json.loads(capsys.readouterr().out)

    assert output["name"] == "project-api"
    assert output["workspace"] == "ws_project"
    assert output["status"] == "Ready"


def test_sandbox_status_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "sandbox_status",
        lambda name: json.dumps(
            {
                "name": name,
                "status": "Ready",
                "workspace": "default",
                "id": "sandbox-id",
                "host_workspace_id": "ws_project",
            }
        ),
    )

    assert cli._sandbox_status("project-api", True) == cli.EXIT_OK

    output = json.loads(capsys.readouterr().out)

    assert output["name"] == "project-api"
    assert output["status"] == "Ready"
    assert output["host_workspace_id"] == "ws_project"


def test_sandbox_status_table(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "sandbox_status",
        lambda name: json.dumps(
            {
                "name": name,
                "status": "Ready",
                "workspace": "default",
                "id": "sandbox-id",
                "host_workspace_id": "ws_project",
            }
        ),
    )

    assert cli._sandbox_status("project-api", False) == cli.EXIT_OK

    output = capsys.readouterr().out

    assert "Name:                project-api" in output
    assert "Status:              Ready" in output
    assert "OpenShell workspace: default" in output
    assert "ID:                  sandbox-id" in output
    assert "Host workspace ID:   ws_project" in output


def test_sandbox_delete_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "delete_sandbox",
        lambda name: json.dumps(
            {
                "name": name,
                "status": "Deleted",
            }
        ),
    )

    assert cli._sandbox_delete("project-api", True) == cli.EXIT_OK

    output = json.loads(capsys.readouterr().out)

    assert output["name"] == "project-api"
    assert output["status"] == "Deleted"


def test_sandbox_delete_table(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "delete_sandbox",
        lambda name: json.dumps({"name": name}),
    )

    assert cli._sandbox_delete("project-api", False) == cli.EXIT_OK

    assert "Sandbox deleted: project-api" in capsys.readouterr().out


def test_sandbox_shell_builds_expected_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "_openshell_command",
        lambda *args: ["openshell", *args],
    )

    def fake_run(command, *, cwd=cli.PROJECT_ROOT, env=None):
        captured["command"] = command
        return 0

    monkeypatch.setattr(cli, "_run_passthrough", fake_run)

    assert cli._sandbox_shell("project-api") == cli.EXIT_OK

    assert captured["command"] == [
        "openshell",
        "sandbox",
        "exec",
        "--name",
        "project-api",
        "--tty",
        "--",
        "/bin/bash",
        "-l",
    ]


def test_sandbox_exec_builds_expected_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "_openshell_command",
        lambda *args: ["openshell", *args],
    )

    monkeypatch.setattr(
        cli,
        "validate_command",
        lambda command: None,
    )

    def fake_run(command, *, cwd=cli.PROJECT_ROOT, env=None):
        captured["command"] = command
        return 0

    monkeypatch.setattr(cli, "_run_passthrough", fake_run)

    assert (
        cli._sandbox_exec(
            "project-api",
            ["--", "echo", "hello"],
        )
        == cli.EXIT_OK
    )

    assert captured["command"] == [
        "openshell",
        "sandbox",
        "exec",
        "--name",
        "project-api",
        "--",
        "echo",
        "hello",
    ]


def test_sandbox_exec_requires_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "validate_command",
        lambda command: None,
    )

    with pytest.raises(
        ValueError,
        match="requires a command",
    ):
        cli._sandbox_exec("project-api", [])


def test_sandbox_logs_builds_expected_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "_openshell_command",
        lambda *args: ["openshell", *args],
    )

    def fake_run(command, *, cwd=cli.PROJECT_ROOT, env=None):
        captured["command"] = command
        return 0

    monkeypatch.setattr(cli, "_run_passthrough", fake_run)

    assert cli._sandbox_logs("project-api") == cli.EXIT_OK

    assert captured["command"] == [
        "openshell",
        "logs",
        "project-api",
    ]


@pytest.mark.parametrize(
    ("helper", "expected"),
    [
        (
            "_sandbox_start",
            ["openshell", "sandbox", "start", "project-api"],
        ),
        (
            "_sandbox_stop",
            ["openshell", "sandbox", "stop", "project-api"],
        ),
    ],
)
def test_sandbox_lifecycle_commands(
    monkeypatch: pytest.MonkeyPatch,
    helper: str,
    expected: list[str],
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "_openshell_command",
        lambda *args: ["openshell", *args],
    )

    def fake_run(command, *, cwd=cli.PROJECT_ROOT, env=None):
        captured["command"] = command
        return 0

    monkeypatch.setattr(cli, "_run_passthrough", fake_run)

    assert getattr(cli, helper)("project-api") == cli.EXIT_OK

    assert captured["command"] == expected


@pytest.mark.parametrize(
    ("argv", "command", "sandbox_command"),
    [
        (["sandbox", "list"], "sandbox", "list"),
        (["sandbox", "status", "project-api"], "sandbox", "status"),
        (
            ["sandbox", "create", "project-api", "--workspace", "ws_project"],
            "sandbox",
            "create",
        ),
        (
            ["sandbox", "create", "standalone-api", "--standalone"],
            "sandbox",
            "create",
        ),
        (["sandbox", "shell", "project-api"], "sandbox", "shell"),
        (
            ["sandbox", "exec", "project-api", "--", "echo", "hello"],
            "sandbox",
            "exec",
        ),
        (["sandbox", "logs", "project-api"], "sandbox", "logs"),
        (["sandbox", "start", "project-api"], "sandbox", "start"),
        (["sandbox", "stop", "project-api"], "sandbox", "stop"),
        (["sandbox", "delete", "project-api"], "sandbox", "delete"),
    ],
)
def test_sandbox_parser_commands(
    argv: list[str],
    command: str,
    sandbox_command: str,
) -> None:
    parser = cli._build_parser()
    args = parser.parse_args(argv)

    assert args.command == command
    assert args.sandbox_command == sandbox_command
    assert callable(args.handler)


def test_sandbox_parser_requires_workspace_source() -> None:
    parser = cli._build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "sandbox",
                "create",
                "project-api",
            ]
        )


def test_sandbox_parser_rejects_conflicting_workspace_sources() -> None:
    parser = cli._build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "sandbox",
                "create",
                "project-api",
                "--workspace",
                "ws_project",
                "--standalone",
            ]
        )


@pytest.mark.parametrize(
    ("argv", "credential_command"),
    [
        (
            [
                "credential",
                "create",
                "github",
                "--type",
                "generic",
                "--key",
                "GITHUB_TOKEN",
                "--yes",
            ],
            "create",
        ),
        (
            ["credential", "list"],
            "list",
        ),
        (
            ["credential", "get", "github"],
            "get",
        ),
        (
            [
                "credential",
                "update",
                "github",
                "--key",
                "GITHUB_TOKEN",
                "--yes",
            ],
            "update",
        ),
        (
            ["credential", "delete", "github", "--yes"],
            "delete",
        ),
        (
            [
                "credential",
                "grant",
                "project-api",
                "github",
                "--yes",
            ],
            "grant",
        ),
        (
            [
                "credential",
                "revoke",
                "project-api",
                "github",
                "--yes",
            ],
            "revoke",
        ),
    ],
)
def test_credential_parser_commands(
    argv: list[str],
    credential_command: str,
) -> None:
    parser = cli._build_parser()
    args = parser.parse_args(argv)

    assert args.command == "credential"
    assert args.credential_command == credential_command
    assert callable(args.handler)


@pytest.mark.parametrize(
    ("helper", "args"),
    [
        ("_credential_create", ("github", "generic", "GITHUB_TOKEN", False)),
        ("_credential_update", ("github", "GITHUB_TOKEN", False)),
        ("_credential_delete", ("github", False)),
        ("_credential_grant", ("project-api", "github", False)),
        ("_credential_revoke", ("project-api", "github", False)),
    ],
)
def test_credential_mutations_require_confirmation(
    helper: str,
    args: tuple[object, ...],
) -> None:
    with pytest.raises(
        ValueError,
        match=r"requires --yes",
    ):
        getattr(cli, helper)(*args)


def test_credential_create_prompts_for_missing_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class TTY:
        def isatty(self) -> bool:
            return True

    answers = iter(["github", "generic", "GITHUB_TOKEN", "y"])
    monkeypatch.setattr(cli.sys, "stdin", TTY())
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    captured: dict[str, str] = {}

    def fake_create(name: str, provider_type: str, credential_key: str) -> int:
        captured.update(name=name, provider_type=provider_type, credential_key=credential_key)
        return 0

    monkeypatch.setattr(cli, "create_credential", fake_create)
    assert cli._credential_create(None, None, None, False) == cli.EXIT_OK
    assert captured == {
        "name": "github",
        "provider_type": "generic",
        "credential_key": "GITHUB_TOKEN",
    }
    assert "Cancelled" not in capsys.readouterr().out


def test_credential_create_decline_does_not_create(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class TTY:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(cli.sys, "stdin", TTY())
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    monkeypatch.setattr(
        cli,
        "create_credential",
        lambda *args: pytest.fail("must not create after decline"),
    )
    assert cli._credential_create("github", "generic", "GITHUB_TOKEN", False) == cli.EXIT_OK
    assert "No credential was created" in capsys.readouterr().out


def test_credential_create_missing_metadata_requires_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NonTTY:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(cli.sys, "stdin", NonTTY())
    with pytest.raises(ValueError, match="stdin is not a terminal"):
        cli._credential_create(None, "generic", "GITHUB_TOKEN", True)


def test_credential_create_non_tty_requires_terminal_for_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NonTTY:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(cli.sys, "stdin", NonTTY())
    with pytest.raises(ValueError, match="terminal for hidden secret input"):
        cli._credential_create("github", "generic", "GITHUB_TOKEN", True)


def test_credential_create_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TTY:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(cli.sys, "stdin", TTY())
    captured: dict[str, object] = {}

    def fake_create(name: str, provider_type: str, credential_key: str) -> int:
        captured.update(
            {
                "name": name,
                "provider_type": provider_type,
                "credential_key": credential_key,
            }
        )
        return 0

    monkeypatch.setattr(cli, "create_credential", fake_create)

    assert (
        cli._credential_create(
            "github",
            "generic",
            "GITHUB_TOKEN",
            True,
        )
        == cli.EXIT_OK
    )

    assert captured == {
        "name": "github",
        "provider_type": "generic",
        "credential_key": "GITHUB_TOKEN",
    }


def test_credential_update_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_update(name: str, credential_key: str) -> int:
        captured.update(
            {
                "name": name,
                "credential_key": credential_key,
            }
        )
        return 0

    monkeypatch.setattr(cli, "update_credential", fake_update)

    assert (
        cli._credential_update(
            "github",
            "GITHUB_TOKEN",
            True,
        )
        == cli.EXIT_OK
    )

    assert captured == {
        "name": "github",
        "credential_key": "GITHUB_TOKEN",
    }


def test_credential_delete_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_delete(name: str) -> int:
        captured["name"] = name
        return 0

    monkeypatch.setattr(cli, "delete_credential", fake_delete)

    assert cli._credential_delete("github", True) == cli.EXIT_OK

    assert captured["name"] == "github"


def test_credential_grant_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_grant(sandbox_name: str, credential_name: str) -> int:
        captured.update(
            {
                "sandbox_name": sandbox_name,
                "credential_name": credential_name,
            }
        )
        return 0

    monkeypatch.setattr(cli, "grant_credential", fake_grant)

    assert (
        cli._credential_grant(
            "project-api",
            "github",
            True,
        )
        == cli.EXIT_OK
    )

    assert captured == {
        "sandbox_name": "project-api",
        "credential_name": "github",
    }


def test_credential_revoke_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_revoke(sandbox_name: str, credential_name: str) -> int:
        captured.update(
            {
                "sandbox_name": sandbox_name,
                "credential_name": credential_name,
            }
        )
        return 0

    monkeypatch.setattr(cli, "revoke_credential", fake_revoke)

    assert (
        cli._credential_revoke(
            "project-api",
            "github",
            True,
        )
        == cli.EXIT_OK
    )

    assert captured == {
        "sandbox_name": "project-api",
        "credential_name": "github",
    }


def test_main_dispatches_sandbox_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_list(json_output: bool) -> int:
        captured["json_output"] = json_output
        return 17

    monkeypatch.setattr(cli, "_sandbox_list", fake_list)

    assert (
        cli.main(
            [
                "sandbox",
                "list",
                "--json",
            ]
        )
        == 17
    )

    assert captured == {"json_output": True}


def test_main_dispatches_sandbox_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(
        name: str,
        workspace_id: str | None,
        standalone: bool,
        json_output: bool,
    ) -> int:
        captured.update(
            {
                "name": name,
                "workspace_id": workspace_id,
                "standalone": standalone,
                "json_output": json_output,
            }
        )
        return 17

    monkeypatch.setattr(cli, "_sandbox_create", fake_create)

    assert (
        cli.main(
            [
                "sandbox",
                "create",
                "standalone-api",
                "--standalone",
                "--json",
            ]
        )
        == 17
    )

    assert captured == {
        "name": "standalone-api",
        "workspace_id": None,
        "standalone": True,
        "json_output": True,
    }


def test_main_dispatches_credential_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_grant(
        sandbox_name: str,
        credential_name: str,
        confirmed: bool,
    ) -> int:
        captured.update(
            {
                "sandbox_name": sandbox_name,
                "credential_name": credential_name,
                "confirmed": confirmed,
            }
        )
        return 17

    monkeypatch.setattr(cli, "_credential_grant", fake_grant)

    assert (
        cli.main(
            [
                "credential",
                "grant",
                "project-api",
                "github",
                "--yes",
            ]
        )
        == 17
    )

    assert captured == {
        "sandbox_name": "project-api",
        "credential_name": "github",
        "confirmed": True,
    }


def test_main_returns_error_for_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def raise_error() -> int:
        raise RuntimeError("docker is unavailable")

    monkeypatch.setattr(cli, "_start", raise_error)

    assert cli.main(["start"]) == cli.EXIT_ERROR

    assert "ERROR: docker is unavailable" in capsys.readouterr().err


def test_main_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])

    assert exc_info.value.code == 0

    output = capsys.readouterr().out

    assert "Local control CLI" in output
    assert "sandbox" in output
    assert "credential" in output
    assert "start" in output
    assert "stop" in output
    assert "restart" in output
    assert "status" in output
    assert "logs" in output



@pytest.mark.parametrize(
    ("infrastructure_ready", "ready", "expected_result", "expected_code"),
    [
        (True, True, "RESULT: START READY", 0),
        (True, False, "RESULT: START DEGRADED", 0),
        (False, False, "RESULT: START FAILED", 2),
    ],
)
def test_started_stack_reports_verified_readiness(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    infrastructure_ready: bool,
    ready: bool,
    expected_result: str,
    expected_code: int,
) -> None:
    from types import SimpleNamespace

    from local_mcp_server.cli import lifecycle

    status = SimpleNamespace(infrastructure_ready=infrastructure_ready, ready=ready)
    monkeypatch.setattr(
        lifecycle,
        "get_status",
        lambda tls_status: status,
    )
    monkeypatch.setattr(lifecycle, "print_status", lambda current: None)
    monkeypatch.setattr(
        "local_mcp_server.infrastructure.openshell.tls.get_status",
        lambda: object(),
    )

    result = cli._verify_started_stack("START")

    assert result == expected_code
    captured = capsys.readouterr()
    assert expected_result in captured.out + captured.err
