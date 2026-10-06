from __future__ import annotations

import pytest


EXPECTED_FIELDS = {
    "operating_system",
    "platform",
    "python_version",
    "python_implementation",
}


@pytest.mark.integration
def test_MCP_SYS_001_call_get_system_info_without_arguments(
    mcp_client,
) -> None:
    result = mcp_client.run(lambda client: client.call_tool("get_system_info"))

    assert result.is_error is False, (
        "Calling get_system_info without arguments should succeed; "
        f"received {result.content!r}"
    )


@pytest.mark.integration
def test_MCP_SYS_002_validate_response_fields(mcp_client) -> None:
    result = mcp_client.call_tool("get_system_info")

    assert isinstance(result, dict), (
        f"Expected a dictionary response, received {type(result).__name__}"
    )
    missing_fields = EXPECTED_FIELDS - result.keys()
    assert not missing_fields, (
        f"System information is missing fields: {sorted(missing_fields)}"
    )


@pytest.mark.integration
def test_MCP_SYS_003_validate_response_value_types(mcp_client) -> None:
    result = mcp_client.call_tool("get_system_info")

    assert isinstance(result, dict), (
        f"Expected a dictionary response, received {type(result).__name__}"
    )
    missing_fields = EXPECTED_FIELDS - result.keys()
    assert not missing_fields, (
        f"System information is missing fields: {sorted(missing_fields)}"
    )

    for field in EXPECTED_FIELDS:
        assert isinstance(result[field], str), (
            f"{field} must be a string, received {type(result[field]).__name__}"
        )


@pytest.mark.integration
def test_MCP_SYS_004_validate_non_empty_values(mcp_client) -> None:
    result = mcp_client.call_tool("get_system_info")

    assert isinstance(result, dict), (
        f"Expected a dictionary response, received {type(result).__name__}"
    )
    missing_fields = EXPECTED_FIELDS - result.keys()
    assert not missing_fields, (
        f"System information is missing fields: {sorted(missing_fields)}"
    )

    for field in EXPECTED_FIELDS:
        value = result[field]
        assert isinstance(value, str) and value.strip(), (
            f"{field} must be a non-empty string, received {value!r}"
        )


@pytest.mark.integration
def test_MCP_SYS_005_reject_unexpected_argument(mcp_client) -> None:
    result = mcp_client.run(
        lambda client: client.call_tool(
            "get_system_info",
            {"unexpected_argument_for_test": "must_be_rejected"},
        )
    )

    assert result.is_error is True, (
        f"get_system_info accepted an unexpected argument; received {result!r}"
    )


@pytest.mark.integration
def test_MCP_SYS_006_repeat_call_without_state_mutation(mcp_client) -> None:
    results = [mcp_client.call_tool("get_system_info") for _ in range(3)]

    assert all(isinstance(result, dict) for result in results), (
        "Every get_system_info call should return a dictionary"
    )

    for index, result in enumerate(results, start=1):
        missing_fields = EXPECTED_FIELDS - result.keys()
        assert not missing_fields, (
            f"Call {index} is missing fields: {sorted(missing_fields)}"
        )
        for field in EXPECTED_FIELDS:
            assert isinstance(result[field], str) and result[field].strip(), (
                f"Call {index} returned an invalid {field}: {result[field]!r}"
            )

    assert results[0] == results[1] == results[2], (
        "Repeated get_system_info calls should return stable environment "
        "information when the server process and environment are unchanged"
    )
