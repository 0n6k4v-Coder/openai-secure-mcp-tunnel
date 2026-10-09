from __future__ import annotations

import json
from typing import Any

import pytest


EXPECTED_ARGUMENTS: dict[str, tuple[set[str], set[str]]] = {
    "get_system_info": (set(), set()),
    "create_sandbox": ({"name"}, {"host_workspace_id", "profile"}),
    "list_sandboxes": (set(), set()),
    "sandbox_status": ({"name"}, set()),
    "sandbox_logs": ({"name"}, {"since"}),
    "start_sandbox": ({"name"}, set()),
    "stop_sandbox": ({"name"}, set()),
    "restart_sandbox": ({"name"}, set()),
    "repair_sandbox": ({"name"}, set()),
    "recreate_sandbox": ({"name"}, set()),
    "delete_sandbox": ({"name"}, set()),
    "execute_sandbox_command": ({"name", "command"}, set()),
    "list_files": ({"sandbox_name"}, set()),
    "read_file": ({"sandbox_name", "relative_path"}, set()),
    "write_to_file": (
        {"sandbox_name", "relative_path", "content"},
        {"overwrite"},
    ),
    "replace_file_content": (
        {"sandbox_name", "relative_path", "target_content", "replacement_content"},
        {"allow_multiple"},
    ),
    "create_directory": ({"sandbox_name", "relative_path"}, set()),
    "rename_path": (
        {"sandbox_name", "relative_path", "new_relative_path"},
        set(),
    ),
    "delete_file": ({"sandbox_name", "relative_path"}, set()),
    "delete_directory": ({"sandbox_name", "relative_path"}, set()),
    "list_authorized_host_workspaces": (set(), set()),
    "execute_chrome_devtools_command": (
        {"sandbox_name", "command"},
        {"arguments"},
    ),
    "discover_site": ({"sandbox_name", "url"}, set()),
    "inspect_page": ({"sandbox_name", "page_id"}, {"selector"}),
    "inspect_runtime": ({"sandbox_name", "page_id"}, set()),
    "inspect_styles": ({"sandbox_name", "page_id"}, {"selector"}),
    "trace_assets": ({"sandbox_name", "page_id"}, set()),
    "trace_interactions": ({"sandbox_name", "page_id"}, set()),
    "capture_screenshot": ({"sandbox_name", "page_id"}, {"full_page"}),
    "analyze_structure": ({"evidence"}, set()),
    "build_dependency_graph": ({"evidence"}, set()),
    "create_clone_manifest": ({"evidence"}, set()),
    "generate_project": ({"sandbox_name"}, {"output_dir", "manifest"}),
    "build_project": ({"sandbox_name"}, {"project_dir"}),
    "serve_project": ({"sandbox_name"}, {"project_dir", "port"}),
    "verify_clone": ({"evidence"}, set()),
    "repair_clone": ({"evidence"}, set()),
    "run_clone_workflow": ({"workflow", "inputs"}, set()),
}

EXPECTED_DEFAULTS: dict[str, dict[str, Any]] = {
    "create_sandbox": {"host_workspace_id": None, "profile": "default"},
    "sandbox_logs": {"since": "5m"},
    "execute_chrome_devtools_command": {"arguments": None},
    "write_to_file": {"overwrite": True},
    "replace_file_content": {"allow_multiple": False},
}

EXPECTED_DESCRIPTION_FRAGMENTS = {
    "get_system_info": "return basic information",
    "create_sandbox": "create an openshell sandbox",
    "list_sandboxes": "list openshell sandboxes",
    "sandbox_status": "return the status",
    "sandbox_logs": "return recent openshell logs",
    "start_sandbox": "start a stopped",
    "stop_sandbox": "stop an openshell sandbox",
    "restart_sandbox": "restart an openshell sandbox",
    "repair_sandbox": "retry startup",
    "recreate_sandbox": "delete and recreate",
    "delete_sandbox": "permanently delete",
    "execute_sandbox_command": "execute a normal command",
    "list_files": "list regular files",
    "read_file": "read a utf-8 text file",
    "write_to_file": "create a new file or overwrite",
    "replace_file_content": "replace target content",
    "create_directory": "create a directory",
    "rename_path": "rename a file or directory",
    "delete_file": "delete a regular file",
    "delete_directory": "delete a directory tree",
    "list_authorized_host_workspaces": "list human-authorized host workspace grants",
    "execute_chrome_devtools_command": "execute a chrome devtools cli command",
}

# Values are (readOnlyHint, destructiveHint, idempotentHint, openWorldHint).
DEFAULT_ANNOTATIONS = (False, False, False, False)
EXPECTED_ANNOTATIONS: dict[str, tuple[bool, bool, bool, bool]] = {
    "get_system_info": (True, False, True, False),
    "create_sandbox": DEFAULT_ANNOTATIONS,
    "list_sandboxes": (True, False, True, False),
    "sandbox_status": (True, False, True, False),
    "sandbox_logs": (True, False, True, False),
    "start_sandbox": (False, False, True, False),
    "stop_sandbox": (False, True, True, False),
    "restart_sandbox": (False, True, False, False),
    "repair_sandbox": (False, False, True, False),
    "recreate_sandbox": (False, True, False, False),
    "delete_sandbox": (False, True, False, False),
    "execute_sandbox_command": (False, True, False, False),
    "list_files": (True, False, True, False),
    "read_file": (True, False, True, False),
    "write_to_file": (False, False, True, False),
    "replace_file_content": (False, False, False, False),
    "create_directory": (False, False, False, False),
    "rename_path": (False, False, False, False),
    "delete_file": (False, True, False, False),
    "delete_directory": (False, True, False, False),
    "list_authorized_host_workspaces": (True, False, True, False),
    "execute_chrome_devtools_command": (False, True, False, True),
}



def _list_tools(mcp_client) -> list[Any]:
    result = mcp_client.run(lambda client: client.list_tools(cache_mode="bypass"))
    return result.tools


def _schema(tool: Any) -> dict[str, Any]:
    schema = tool.input_schema
    assert isinstance(schema, dict), f"{tool.name}: input_schema must be an object"
    return schema


@pytest.mark.integration
def test_MCP_REG_001_list_all_registered_tools(mcp_client) -> None:
    tools = _list_tools(mcp_client)
    names = {tool.name for tool in tools}
    assert names == set(EXPECTED_ARGUMENTS)


@pytest.mark.integration
def test_MCP_REG_002_verify_exact_tool_count(mcp_client) -> None:
    assert len(_list_tools(mcp_client)) == len(EXPECTED_ARGUMENTS)


@pytest.mark.integration
def test_MCP_REG_003_verify_tool_names(mcp_client) -> None:
    assert {tool.name for tool in _list_tools(mcp_client)} == set(EXPECTED_ARGUMENTS)


@pytest.mark.integration
def test_MCP_REG_004_verify_tool_names_are_unique(mcp_client) -> None:
    names = [tool.name for tool in _list_tools(mcp_client)]
    assert len(names) == len(set(names))


@pytest.mark.integration
def test_MCP_REG_005_verify_tool_descriptions(mcp_client) -> None:
    tools = {tool.name: tool for tool in _list_tools(mcp_client)}
    assert set(tools) == set(EXPECTED_DESCRIPTION_FRAGMENTS)
    for name, fragment in EXPECTED_DESCRIPTION_FRAGMENTS.items():
        description = tools[name].description
        assert isinstance(description, str) and len(description.strip()) >= 15, (
            f"{name}: missing or unhelpful description"
        )
        assert fragment in description.lower(), (
            f"{name}: description {description!r} does not describe its behavior"
        )


@pytest.mark.integration
def test_MCP_REG_006_verify_input_schemas(mcp_client) -> None:
    for tool in _list_tools(mcp_client):
        schema = _schema(tool)
        assert schema.get("type") == "object", f"{tool.name}: expected object schema"
        assert isinstance(schema.get("properties"), dict), (
            f"{tool.name}: properties must be an object"
        )
        assert isinstance(schema.get("required", []), list), (
            f"{tool.name}: required must be an array"
        )
        assert all(isinstance(item, str) for item in schema.get("required", [])), (
            f"{tool.name}: required entries must be strings"
        )
        # Ensure the advertised schema is valid JSON data (no unsupported values).
        json.dumps(schema, allow_nan=False)


@pytest.mark.integration
def test_MCP_REG_007_verify_required_arguments(mcp_client) -> None:
    for tool in _list_tools(mcp_client):
        schema = _schema(tool)
        properties = schema["properties"]
        required = set(schema.get("required", []))
        expected_required, expected_optional = EXPECTED_ARGUMENTS[tool.name]
        assert required == expected_required, (
            f"{tool.name}: required fields {required!r}, expected {expected_required!r}"
        )
        assert set(properties) == expected_required | expected_optional, (
            f"{tool.name}: properties do not match the registered signature"
        )


@pytest.mark.integration
def test_MCP_REG_008_verify_optional_arguments_and_defaults(mcp_client) -> None:
    tools = {tool.name: tool for tool in _list_tools(mcp_client)}
    for name, defaults in EXPECTED_DEFAULTS.items():
        properties = _schema(tools[name])["properties"]
        for argument, expected in defaults.items():
            assert argument in properties, (
                f"{name}: missing optional argument {argument}"
            )
            if "default" in properties[argument]:
                assert properties[argument]["default"] == expected, (
                    f"{name}.{argument}: advertised default differs from implementation"
                )
            elif expected is not None:
                pytest.fail(
                    f"{name}.{argument}: expected advertised default {expected!r}"
                )


@pytest.mark.integration
def test_MCP_REG_009_verify_tool_annotations(mcp_client) -> None:
    tools = {tool.name: tool for tool in _list_tools(mcp_client)}
    assert set(tools) == set(EXPECTED_ANNOTATIONS)
    for name, expected in EXPECTED_ANNOTATIONS.items():
        annotations = tools[name].annotations
        assert annotations is not None, f"{name}: annotations are missing"
        actual = (
            annotations.read_only_hint,
            annotations.destructive_hint,
            annotations.idempotent_hint,
            annotations.open_world_hint,
        )
        assert actual == expected, (
            f"{name}: annotations {actual!r}, expected {expected!r}"
        )


@pytest.mark.integration
def test_MCP_REG_010_verify_registry_stability(mcp_client) -> None:
    first = [tool.name for tool in _list_tools(mcp_client)]
    second = [tool.name for tool in _list_tools(mcp_client)]
    assert first == second, (
        "Tool order or names changed between unchanged registry listings"
    )


@pytest.mark.integration
def test_MCP_REG_011_call_unknown_tool_name(mcp_client) -> None:
    unknown_name = "mcp_registry_unknown_tool_for_test"
    try:
        result = mcp_client.run(
            lambda client: client.call_tool(unknown_name, arguments={})
        )
    except Exception as exc:
        assert unknown_name in str(exc) or "unknown" in str(exc).lower(), (
            f"Unknown-tool failure did not identify the problem: {exc!r}"
        )
    else:
        assert result.is_error, (
            f"Unknown tool {unknown_name!r} unexpectedly succeeded: {result!r}"
        )


@pytest.mark.integration
def test_MCP_REG_012_verify_unsupported_capabilities(mcp_client) -> None:
    capabilities = mcp_client.run(lambda client: client.server_capabilities)
    assert capabilities is not None and capabilities.tools is not None

    # Resources and prompts are advertised by the current server implementation.
    # Reject only capabilities that are not supported by this server.
    advertised = capabilities.model_dump(exclude_none=True)
    for unsupported in ("completions", "experimental", "extensions"):
        assert unsupported not in advertised, (
            f"Server advertises unsupported capability {unsupported!r}"
        )


@pytest.mark.integration
def test_MCP_REG_013_package_installation_tool_is_not_exposed(mcp_client) -> None:
    names = {tool.name for tool in _list_tools(mcp_client)}
    assert "request_tool_installation" not in names
    assert "execute_sandbox_command" in names
