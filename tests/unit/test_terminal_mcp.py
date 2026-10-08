from mcp.server import MCPServer
from mcp.server.apps import Apps

from local_mcp_server.mcp.apps.registration import register_all_apps
from local_mcp_server.mcp.apps.terminal import TERMINAL_APP_URI
from local_mcp_server.mcp.registration import register_all_tools


def test_mcp_terminal_tools_registered():
    apps = Apps()
    register_all_apps(apps)
    mcp = MCPServer("test", extensions=[apps])
    register_all_tools(mcp)

    tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
    expected_tools = [
        "terminal_open",
        "terminal_input",
        "terminal_resize",
        "terminal_state",
        "terminal_close",
        "terminal_list",
    ]
    for exp in expected_tools:
        assert exp in tool_names, f"Expected tool {exp} to be registered"

    # Verify that terminal_open carries the MCP App UI resource URI
    terminal_open_tool = next(t for t in mcp._tool_manager.list_tools() if t.name == "terminal_open")
    assert terminal_open_tool.meta is not None
    assert terminal_open_tool.meta.get("ui", {}).get("resourceUri") == TERMINAL_APP_URI


def test_mcp_terminal_app_resource_registered(monkeypatch):
    monkeypatch.delenv("MCP_TERMINAL_APP_DOMAIN", raising=False)
    apps = Apps()
    register_all_apps(apps)
    resource_entry = next(r for r in apps._resources if r.resource.uri == TERMINAL_APP_URI)
    assert resource_entry.resource.meta is not None
    domain = resource_entry.resource.meta.get("ui", {}).get("domain")
    assert domain == "https://terminal.openai-secure-mcp-tunnel.internal"
    assert domain.startswith("https://")

    # Verify custom domain configuration via environment variable
    custom_domain = "https://terminal.example.com"
    monkeypatch.setenv("MCP_TERMINAL_APP_DOMAIN", custom_domain)
    apps_custom = Apps()
    register_all_apps(apps_custom)
    custom_entry = next(r for r in apps_custom._resources if r.resource.uri == TERMINAL_APP_URI)
    assert custom_entry.resource.meta.get("ui", {}).get("domain") == custom_domain
