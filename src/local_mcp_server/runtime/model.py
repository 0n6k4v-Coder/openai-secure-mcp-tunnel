from __future__ import annotations

import re
from dataclasses import dataclass

_RUNTIME_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


def validate_runtime_name(value: str) -> str:
    if not isinstance(value, str) or not _RUNTIME_NAME.fullmatch(value):
        raise ValueError(
            "Runtime name must start with a lowercase letter and contain only "
            "lowercase letters, digits, and hyphens (maximum 31 characters)."
        )
    if value in {"default", "runtimes", "profiles"}:
        raise ValueError(f"Runtime name {value!r} is reserved.")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    name: str
    compose_project_name: str
    openshell_workspace: str
    description: str = ""

    def __post_init__(self) -> None:
        if self.name != "default":
            validate_runtime_name(self.name)
        for field_name, value in (
            ("compose_project_name", self.compose_project_name),
            ("openshell_workspace", self.openshell_workspace),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}", value):
                raise ValueError(f"Invalid {field_name}.")
        if not isinstance(self.description, str) or len(self.description) > 256:
            raise ValueError("Runtime description must be at most 256 characters.")

    @classmethod
    def default(cls) -> "RuntimeProfile":
        return cls(
            name="default",
            compose_project_name="openai-secure-mcp-tunnel",
            openshell_workspace="default",
            description="Default shared runtime (legacy paths).",
        )

    @classmethod
    def named(cls, name: str, description: str = "") -> "RuntimeProfile":
        validate_runtime_name(name)
        return cls(
            name=name,
            compose_project_name=f"openai-secure-mcp-tunnel-{name}",
            openshell_workspace=f"mcp-{name}",
            description=description,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "compose_project_name": self.compose_project_name,
            "openshell_workspace": self.openshell_workspace,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RuntimeProfile":
        if not isinstance(value, dict):
            raise ValueError("Runtime registry entry must be an object.")
        return cls(
            name=value.get("name", ""),
            compose_project_name=value.get("compose_project_name", ""),
            openshell_workspace=value.get("openshell_workspace", ""),
            description=value.get("description", ""),
        )
