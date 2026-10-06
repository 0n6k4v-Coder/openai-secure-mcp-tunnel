from __future__ import annotations

from .model import RuntimeProfile, validate_runtime_name


def runtime_template(name: str, description: str = "") -> dict[str, object]:
    """Return a safe, path-free template for a named runtime."""
    validate_runtime_name(name)
    profile = RuntimeProfile.named(name, description)
    return {
        "schema_version": 1,
        "runtime": profile.to_dict(),
        "isolation": {
            "configuration": "XDG_CONFIG_HOME/local-mcp-server/runtimes/<name>",
            "state": "XDG_STATE_HOME/local-mcp-server/runtimes/<name>",
            "compose_project": profile.compose_project_name,
            "openshell_workspace": profile.openshell_workspace,
        },
    }


def default_template() -> dict[str, object]:
    return {
        "schema_version": 1,
        "runtime": RuntimeProfile.default().to_dict(),
        "isolation": {
            "configuration": "legacy XDG application configuration",
            "state": "legacy XDG application state",
            "compose_project": RuntimeProfile.default().compose_project_name,
            "openshell_workspace": "default",
        },
    }
