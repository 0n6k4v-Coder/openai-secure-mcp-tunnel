
from mcp.server import MCPServer

from local_mcp_server.mcp.apps.registration import register_all_apps
from local_mcp_server.mcp.apps.terminal import TERMINAL_APP_URI
from local_mcp_server.mcp.registration import register_all_tools


def test_mcp_terminal_tools_registered():
    mcp = MCPServer("test")
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


def test_mcp_terminal_app_resource_registered():
    from mcp.server.apps import Apps

    apps = Apps()
    register_all_apps(apps)
    # Check that the app resource was added
    uris = [r.resource.uri for r in apps._resources]
    assert TERMINAL_APP_URI in uris
