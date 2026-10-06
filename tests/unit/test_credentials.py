from __future__ import annotations

import subprocess

import pytest

from local_mcp_server.infrastructure.openshell import credentials as service


def test_validate_provider_name() -> None:
    assert service._validate_provider_name("my-openai") == "my-openai"

    with pytest.raises(ValueError):
        service._validate_provider_name("My-OpenAI")

    with pytest.raises(ValueError):
        service._validate_provider_name("")


def test_validate_provider_type() -> None:
    assert service._validate_provider_type("openai") == "openai"

    with pytest.raises(ValueError):
        service._validate_provider_type("OpenAI")


def test_validate_credential_key() -> None:
    assert service._validate_credential_key("OPENAI_API_KEY") == "OPENAI_API_KEY"

    with pytest.raises(ValueError):
        service._validate_credential_key("openai_api_key")

    with pytest.raises(ValueError):
        service._validate_credential_key("1KEY")


def test_command_exists_accepts_installed_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service.shutil, "which", lambda command: "/usr/bin/openshell")

    service._command_exists("openshell")


def test_command_exists_rejects_missing_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service.shutil, "which", lambda command: None)

    with pytest.raises(
        service.CredentialError,
        match="Required command 'openshell' is not installed or is not on PATH",
    ):
        service._command_exists("openshell")


def test_gateway_endpoint_defaults_to_https() -> None:
    assert service._gateway_endpoint() == "https://127.0.0.1:8080"


def test_gateway_endpoint_adds_http_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        service.GATEWAY_ENDPOINT_ENV,
        "127.0.0.1:8080",
    )

    assert service._gateway_endpoint() == "http://127.0.0.1:8080"


def test_create_credential_does_not_put_secret_in_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_command_exists", lambda command: None)
    monkeypatch.setattr(
        service.getpass,
        "getpass",
        lambda prompt: "super-secret",
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        shell: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["env"] = env
        captured["shell"] = shell
        captured["capture_output"] = capture_output

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="provider created",
            stderr="",
        )

    monkeypatch.setattr(
        service.subprocess,
        "run",
        fake_run,
    )

    assert service.create_credential("my-openai", "openai", "OPENAI_API_KEY") == 0

    assert captured["command"] == [
        "openshell",
        "--gateway",
        "local",
        "provider",
        "create",
        "--name",
        "my-openai",
        "--type",
        "openai",
        "--credential",
        "OPENAI_API_KEY",
    ]

    assert "super-secret" not in captured["command"]
    assert captured["env"]["OPENAI_API_KEY"] == "super-secret"
    assert captured["shell"] is False


def test_update_credential_uses_environment_not_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_command_exists", lambda command: None)
    monkeypatch.setattr(
        service.getpass,
        "getpass",
        lambda prompt: "rotated-secret",
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        shell: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["env"] = env
        captured["shell"] = shell

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="updated",
            stderr="",
        )

    monkeypatch.setattr(
        service.subprocess,
        "run",
        fake_run,
    )

    assert service.update_credential("my-openai", "OPENAI_API_KEY") == 0

    assert captured["command"] == [
        "openshell",
        "--gateway",
        "local",
        "provider",
        "update",
        "my-openai",
        "--credential",
        "OPENAI_API_KEY",
    ]

    assert captured["env"]["OPENAI_API_KEY"] == "rotated-secret"
    assert captured["shell"] is False


def test_grant_credential_uses_provider_attach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_command_exists", lambda command: None)

    def fake_run(
        command: list[str],
        *,
        check: bool,
        shell: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["shell"] = shell
        captured["timeout"] = timeout

        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        service.subprocess,
        "run",
        fake_run,
    )

    assert service.grant_credential("sandbox-one", "github") == 0

    assert captured["command"] == [
        "openshell",
        "--gateway",
        "local",
        "sandbox",
        "provider",
        "attach",
        "sandbox-one",
        "github",
        "--wait",
        "--timeout",
        "30",
    ]

    assert captured["shell"] is False


def test_revoke_credential_uses_provider_detach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_command_exists", lambda command: None)

    def fake_run(
        command: list[str],
        *,
        check: bool,
        shell: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["shell"] = shell
        captured["timeout"] = timeout

        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        service.subprocess,
        "run",
        fake_run,
    )

    assert service.revoke_credential("sandbox-one", "github") == 0

    assert captured["command"] == [
        "openshell",
        "--gateway",
        "local",
        "sandbox",
        "provider",
        "detach",
        "sandbox-one",
        "github",
        "--wait",
        "--timeout",
        "30",
    ]

    assert captured["shell"] is False
