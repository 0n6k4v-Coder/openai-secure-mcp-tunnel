from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from local_mcp_server.installation import service
from local_mcp_server.installation import tools as installation_tools


def _request(
    *,
    sandbox_name: str = "my-sandbox",
    tool_name: str = "uv",
    version: str = "latest",
    source: str = "official Astral uv release",
    install_command: str = "uv tool install uv",
    reason: str = "Required to run repository tooling.",
) -> service.InstallationRequest:
    return service.create_installation_request(
        sandbox_name=sandbox_name,
        tool_name=tool_name,
        version=version,
        source=source,
        install_command=install_command,
        reason=reason,
    )


def test_create_installation_request_persists_pending_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    request = _request()

    state = json.loads(state_file.read_text(encoding="utf-8"))

    assert state[request.request_id]["state"] == "pending"
    assert state[request.request_id]["sandbox_name"] == "my-sandbox"
    assert state[request.request_id]["tool_name"] == "uv"


def test_approval_is_single_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    request = _request()
    service.approve_installation(request.request_id)

    consumed = service.consume_installation_approval(request.request_id)

    assert consumed.request_id == request.request_id

    with pytest.raises(
        service.InstallationError,
        match="has not been approved",
    ):
        service.consume_installation_approval(request.request_id)


def test_install_command_rejects_shell_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    dangerous_commands = (
        "uv tool install uv; touch /tmp/pwned",
        "uv tool install uv && touch /tmp/pwned",
        "uv tool install uv | sh",
        "uv tool install $(touch /tmp/pwned)",
        "uv tool install uv > /tmp/output",
        "uv tool install $HOME",
        "bash -c 'echo unsafe'",
        "/tmp/uv tool install uv",
    )

    for command in dangerous_commands:
        with pytest.raises(service.InstallationError):
            _request(install_command=command)


def test_install_command_accepts_supported_package_managers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    commands = (
        "apt-get install -y jq",
        "apt install -y jq",
        "dnf install -y jq",
        "yum install -y jq",
        "apk add jq",
        "pip install ruff==0.13.0",
        "pip3 install ruff==0.13.0",
        "pipx install ruff",
        "uv tool install ruff==0.13.0",
        "uv pip install ruff==0.13.0",
        "npm install -g typescript",
        "pnpm add -g typescript",
        "yarn add -g typescript",
        "cargo install ripgrep",
        "go install golang.org/x/tools/gopls@latest",
        "gem install bundler",
        "composer require phpunit/phpunit",
        "conda install -y jq",
    )

    for index, command in enumerate(commands):
        request = _request(
            tool_name=f"tool-{index}",
            install_command=command,
        )
        assert request.install_command == command


def test_chrome_devtools_install_commands_are_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    for version in ("latest", "1.10.1"):
        request = _request(
            tool_name="chrome-devtools-mcp",
            version=version,
            source="npm",
            install_command=(f"npm install -g chrome-devtools-mcp@{version}"),
            reason="Required for Chrome DevTools MCP integration testing.",
        )

        assert request.tool_name == "chrome-devtools-mcp"
        assert request.version == version
        assert request.install_command == (
            f"npm install -g chrome-devtools-mcp@{version}"
        )


def test_execute_installation_runs_only_after_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    class FakeResult:
        exit_code = 0
        stdout = "installed"
        stderr = ""

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def exec(
            self,
            name,
            command,
            *,
            workspace,
            timeout_seconds,
            no_login_shell,
        ):
            assert name == "my-sandbox"
            assert command == ["uv", "tool", "install", "uv"]
            assert no_login_shell is True
            assert timeout_seconds == 300
            return FakeResult()

    class FakeSandboxClient:
        @classmethod
        def from_active_cluster(cls):
            return FakeClient()

    monkeypatch.setattr(
        service,
        "active_client",
        FakeSandboxClient.from_active_cluster,
    )

    request = _request()

    with pytest.raises(
        service.InstallationError,
        match="has not been approved",
    ):
        service.execute_installation(request)

    service.approve_installation(request.request_id)

    result = service.execute_installation(request)

    assert result["approved"] is True
    assert result["executed"] is True
    assert result["success"] is True
    assert result["sandbox_name"] == "my-sandbox"

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state[request.request_id]["state"] == "completed"


def test_failed_installation_is_recorded_and_raised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    class FakeResult:
        exit_code = 1
        stdout = ""
        stderr = "package manager failed"

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def exec(self, *args, **kwargs):
            return FakeResult()

    class FakeSandboxClient:
        @classmethod
        def from_active_cluster(cls):
            return FakeClient()

    monkeypatch.setattr(
        service,
        "active_client",
        FakeSandboxClient.from_active_cluster,
    )

    request = _request()
    service.approve_installation(request.request_id)

    with pytest.raises(
        service.InstallationError,
        match="exit code 1: package manager failed",
    ):
        service.execute_installation(request)

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state[request.request_id]["state"] == "failed"


def test_mcp_tool_exposes_installation_validation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    mcp = MCPServer("installation-test")
    installation_tools.register_tools(mcp)

    with pytest.raises(
        ToolError,
        match="Invalid sandbox name",
    ):
        asyncio.run(
            mcp.call_tool(
                "request_tool_installation",
                {
                    "sandbox_name": "INVALID",
                    "tool_name": "chrome-devtools-mcp",
                    "version": "1.10.1",
                    "source": "npm",
                    "install_command": ("npm install -g chrome-devtools-mcp@1.10.1"),
                    "reason": "Test validation error visibility.",
                },
            )
        )


def test_mcp_tool_exposes_installation_execution_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "installations.json"
    monkeypatch.setattr(service, "INSTALLATION_STATE_FILE", state_file)

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def exec(self, *args, **kwargs):
            raise RuntimeError("gateway execution unavailable")

    class FakeSandboxClient:
        @classmethod
        def from_active_cluster(cls):
            return FakeClient()

    monkeypatch.setattr(
        service,
        "active_client",
        FakeSandboxClient.from_active_cluster,
    )

    mcp = MCPServer("installation-test")
    installation_tools.register_tools(mcp)

    with pytest.raises(
        ToolError,
        match="gateway execution unavailable",
    ):
        asyncio.run(
            mcp.call_tool(
                "request_tool_installation",
                {
                    "sandbox_name": "my-sandbox",
                    "tool_name": "chrome-devtools-mcp",
                    "version": "1.10.1",
                    "source": "npm",
                    "install_command": ("npm install -g chrome-devtools-mcp@1.10.1"),
                    "reason": "Test execution error visibility.",
                },
            )
        )

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(state) == 1
    request_state = next(iter(state.values()))
    assert request_state["state"] == "failed"
