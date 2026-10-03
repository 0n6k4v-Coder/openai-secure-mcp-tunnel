from __future__ import annotations

import asyncio
import json

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from local_mcp_server.chrome_devtools import service
from local_mcp_server.chrome_devtools import tools as chrome_devtools_tools


def test_command_rejects_shell_syntax() -> None:
    with pytest.raises(service.ChromeDevToolsError):
        service._validate_command("list_pages;")


def test_command_rejects_browser_endpoint_override() -> None:
    for arguments in (
        ["--browserUrl=http://127.0.0.1:9999"],
        ["--browser-url", "http://127.0.0.1:9999"],
    ):
        with pytest.raises(
            service.ChromeDevToolsError,
            match="cannot be overridden",
        ):
            service._validate_arguments(arguments)


def test_command_rejects_cli_lifecycle_commands() -> None:
    for command in ("start", "stop", "status"):
        with pytest.raises(
            service.ChromeDevToolsError,
            match="not available",
        ):
            service._validate_command(command)


def test_execute_uses_existing_browser_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "sandbox_status",
        lambda name: json.dumps(
            {
                "name": name,
                "profile": "browser",
            }
        ),
    )

    calls: list[tuple[str, list[str]]] = []

    def fake_execute(
        name: str,
        argv: list[str],
        *,
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append((name, argv))
        assert timeout_seconds == 120
        return {
            "return_code": 0,
            "stdout": "pages",
            "stderr": "",
        }

    monkeypatch.setattr(
        service,
        "execute_sandbox_argv",
        fake_execute,
    )

    result = service.execute_chrome_devtools(
        sandbox_name="clone-web",
        command="list_pages",
    )

    assert calls == [
        (
            "clone-web",
            [
                "chrome-devtools",
                "list_pages",
            ],
        )
    ]
    assert result["browser_url"] == "http://127.0.0.1:9222"
    assert result["sandbox_name"] == "clone-web"
    assert result["return_code"] == 0
    assert result["stdout"] == "pages"


def test_execute_rejects_non_browser_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "sandbox_status",
        lambda name: json.dumps(
            {
                "name": name,
                "profile": "default",
            }
        ),
    )

    with pytest.raises(
        service.ChromeDevToolsError,
        match="not a browser sandbox",
    ):
        service.execute_chrome_devtools(
            sandbox_name="default-one",
            command="list_pages",
        )


def test_mcp_tool_exposes_validation_errors() -> None:
    mcp = MCPServer("chrome-devtools-test")
    chrome_devtools_tools.register_tools(mcp)

    with pytest.raises(
        ToolError,
        match="Error executing tool execute_chrome_devtools_command",
    ) as exc_info:
        asyncio.run(
            mcp.call_tool(
                "execute_chrome_devtools_command",
                {
                    "sandbox_name": "clone-web",
                    "command": "list_pages",
                    "arguments": [
                        "--browser-url=http://127.0.0.1:9222"
                    ],
                },
            )
        )

    assert exc_info.value.__cause__ is not None
    assert "cannot be overridden" in str(exc_info.value.__cause__)
