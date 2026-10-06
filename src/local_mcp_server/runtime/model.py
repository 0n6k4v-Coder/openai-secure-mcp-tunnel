from __future__ import annotations

import re
import zlib
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
    mcp_port: int = 8000
    openshell_port: int = 8080
    openshell_health_port: int = 8081

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
        ports = (self.mcp_port, self.openshell_port, self.openshell_health_port)
        if any(not isinstance(port, int) or not 1 <= port <= 65535 for port in ports):
            raise ValueError("Runtime ports must be integers between 1 and 65535.")
        if len(set(ports)) != len(ports):
            raise ValueError("Runtime ports must be distinct.")

    @classmethod
    def default(cls) -> "RuntimeProfile":
        return cls(
            name="default",
            compose_project_name="openai-secure-mcp-tunnel",
            openshell_workspace="default",
            description="Default shared runtime (legacy paths).",
            mcp_port=8000,
            openshell_port=8080,
            openshell_health_port=8081,
        )

    @classmethod
    def named(cls, name: str, description: str = "") -> "RuntimeProfile":
        validate_runtime_name(name)
        offset = zlib.crc32(name.encode("utf-8")) % 1000
        return cls(
            name=name,
            compose_project_name=f"openai-secure-mcp-tunnel-{name}",
            openshell_workspace=f"mcp-{name}",
            description=description,
            mcp_port=18000 + offset,
            openshell_port=28080 + offset,
            openshell_health_port=29080 + offset,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "compose_project_name": self.compose_project_name,
            "openshell_workspace": self.openshell_workspace,
            "description": self.description,
            "mcp_port": self.mcp_port,
            "openshell_port": self.openshell_port,
            "openshell_health_port": self.openshell_health_port,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RuntimeProfile":
        if not isinstance(value, dict):
            raise ValueError("Runtime registry entry must be an object.")
        name = value.get("name", "")
        if name == "default":
            fallback = cls.default()
        else:
            fallback = cls.named(name, value.get("description", ""))
        return cls(
            name=name,
            compose_project_name=value.get("compose_project_name", fallback.compose_project_name),
            openshell_workspace=value.get("openshell_workspace", fallback.openshell_workspace),
            description=value.get("description", fallback.description),
            mcp_port=value.get("mcp_port", fallback.mcp_port),
            openshell_port=value.get("openshell_port", fallback.openshell_port),
            openshell_health_port=value.get("openshell_health_port", fallback.openshell_health_port),
        )
