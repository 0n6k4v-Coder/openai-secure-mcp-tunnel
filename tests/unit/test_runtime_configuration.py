from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"


def _read_env_file(name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator, f"Invalid environment assignment in {name}: {raw_line}"
        values[key] = value
    return values


def test_default_environment_is_production() -> None:
    default = _read_env_file(".env.example")
    production = _read_env_file(".env.production.example")

    assert default == production
    assert default["COMPOSE_PROJECT_NAME"].endswith("-production")
    assert default["OPENSHELL_WORKSPACE"] == "production"
    assert default["OPENSHELL_CLI_GATEWAY"] == "https://127.0.0.1:8080"
    assert default["OPENSHELL_CONTAINER_GATEWAY"] == "https://openshell-gateway:8080"
    assert default["LOG_LEVEL"] == "INFO"
    assert default["MCP_CONFIG_DIR"].endswith("/local-mcp-server/config/production")
    assert default["MCP_STATE_DIR"].endswith("/local-mcp-server/mcp/production")
    assert default["WORKSPACE_GRANTS_DIR"].endswith(
        "/local-mcp-server/mcp/production/workspace-grants"
    )


def test_development_environment_is_isolated_and_uses_container_gateway() -> None:
    development = _read_env_file(".env.development.example")
    production = _read_env_file(".env.production.example")

    assert development["COMPOSE_PROJECT_NAME"].endswith("-development")
    assert development["OPENSHELL_WORKSPACE"] == "development"
    assert development["OPENSHELL_CLI_GATEWAY"] == "https://127.0.0.1:18080"
    assert development["OPENSHELL_CONTAINER_GATEWAY"] == "https://openshell-gateway:8080"
    assert development["OPENSHELL_PORT"] == "18080"
    assert development["OPENSHELL_HEALTH_PORT"] == "18081"
    assert development["MCP_PORT"] == "18000"
    assert development["LOG_LEVEL"] == "DEBUG"

    for key in ("MCP_CONFIG_DIR", "MCP_STATE_DIR", "WORKSPACE_GRANTS_DIR"):
        assert "/development" in development[key]
        assert "/production" not in development[key]
        assert development[key] != production[key]


def test_compose_uses_container_gateway_variable() -> None:
    compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")

    assert "OPENSHELL_CLI_GATEWAY: ${OPENSHELL_CONTAINER_GATEWAY:-https://openshell-gateway:8080}" in compose
    assert "OPENSHELL_CLI_GATEWAY: ${OPENSHELL_CLI_GATEWAY" not in compose


def test_smoke_test_uses_an_allowed_health_host() -> None:
    smoke_test = (ROOT / "scripts" / "smoke-test.sh").read_text(encoding="utf-8")

    assert "--header 'Host: 127.0.0.1:8000'" in smoke_test
