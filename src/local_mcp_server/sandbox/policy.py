from __future__ import annotations

import os
import re
from typing import Literal

from openshell._proto import openshell_pb2

from ..workspace.repository import get_workspace_grant


SANDBOX_WORKSPACE_ROOT = "/workspace/project"

SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE",
    "local-mcp-openshell-sandbox:1.0.0",
)

BROWSER_SANDBOX_IMAGE = os.environ.get(
    "BROWSER_SANDBOX_IMAGE",
    "local-mcp-browser-sandbox:1.0.0",
)

DEFAULT_CPU = os.environ.get(
    "SANDBOX_DEFAULT_CPU",
    "1",
)

DEFAULT_MEMORY = os.environ.get(
    "SANDBOX_DEFAULT_MEMORY",
    "1Gi",
)

MAX_COMMAND_BYTES = 32 * 1024
MAX_SANDBOX_NAME_LENGTH = 19

SandboxProfile = Literal["default", "browser"]

_SANDBOX_NAME = re.compile(rf"^[a-z0-9][a-z0-9-]{{0,{MAX_SANDBOX_NAME_LENGTH - 1}}}$")

_CPU_QUANTITY = re.compile(r"^(?:\d+(?:\.\d+)?|\d+m)$")

_MEMORY_QUANTITY = re.compile(r"^\d+(?:\.\d+)?(?:Ki|Mi|Gi|Ti|Pi|Ei|K|M|G|T|P|E)$")

_ENDPOINT = re.compile(r"^(?P<host>[A-Za-z0-9*.-]+):(?P<port>[1-9][0-9]{0,4})$")

_NPM_NODE_BINARY = "/usr/local/bin/node"
_NPM_REGISTRY_HOST = "registry.npmjs.org"
_NPM_REGISTRY_PORT = 443
_NPM_AUDIT_PATHS = (
    "/-/npm/v1/security/advisories/bulk",
    "/-/npm/v1/security/audits/quick",
)

_BROWSER_BINARY = "/opt/chrome/chrome"

_DEFAULT_BROWSER_ENDPOINTS = (
    "host.openshell.internal:4173",
    "mtioon.com:443",
    "www.mtioon.com:443",
)


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not _SANDBOX_NAME.fullmatch(name):
        actual = repr(name) if isinstance(name, str) else type(name).__name__
        length_hint = f" (received {len(name)} chars: {actual})" if isinstance(name, str) else f" (received {actual})"
        raise ValueError(
            "sandbox name must contain only lowercase letters, digits, "
            "and hyphens, start with a letter or digit, and be at most "
            f"{MAX_SANDBOX_NAME_LENGTH} characters{length_hint}"
        )

    return name


def validate_profile(profile: str) -> SandboxProfile:
    if profile not in {"default", "browser"}:
        raise ValueError("sandbox profile must be either 'default' or 'browser'")

    return profile  # type: ignore[return-value]


def validate_cpu(value: str) -> str:
    if not isinstance(value, str) or not _CPU_QUANTITY.fullmatch(value):
        raise ValueError(
            "CPU must be a Kubernetes-style quantity such as 500m, 1, or 2.5"
        )

    return value


def validate_memory(value: str) -> str:
    if not isinstance(value, str) or not _MEMORY_QUANTITY.fullmatch(value):
        raise ValueError("memory must be a quantity such as 512Mi, 4Gi, or 8G")

    return value


def validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must not be empty")

    if len(command.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise ValueError(f"command exceeds {MAX_COMMAND_BYTES} bytes")

    return command


def _browser_endpoints() -> tuple[tuple[str, int], ...]:
    raw = os.environ.get(
        "BROWSER_ALLOWED_ENDPOINTS",
        ",".join(_DEFAULT_BROWSER_ENDPOINTS),
    )

    endpoints: list[tuple[str, int]] = []

    for item in raw.split(","):
        value = item.strip()

        if not value:
            continue

        match = _ENDPOINT.fullmatch(value)

        if match is None:
            raise ValueError(
                "BROWSER_ALLOWED_ENDPOINTS entries must use host:port format."
            )

        host = match.group("host")
        port = int(match.group("port"))

        if port > 65535:
            raise ValueError("BROWSER_ALLOWED_ENDPOINTS contains an invalid port.")

        endpoints.append((host, port))

    if not endpoints:
        raise ValueError(
            "BROWSER_ALLOWED_ENDPOINTS must contain at least one endpoint."
        )

    return tuple(dict.fromkeys(endpoints))


def _add_npm_policy(
    spec: openshell_pb2.SandboxSpec,
) -> None:
    npm_policy = spec.policy.network_policies["npm_registry"]
    npm_policy.name = "npm-registry"

    npm_endpoint = npm_policy.endpoints.add()
    npm_endpoint.host = _NPM_REGISTRY_HOST
    npm_endpoint.port = _NPM_REGISTRY_PORT
    npm_endpoint.protocol = "rest"
    npm_endpoint.enforcement = "NETWORK_ENFORCEMENT_MODE_ENFORCE"
    npm_endpoint.allow_encoded_slash = True

    for method in ("GET", "HEAD", "OPTIONS"):
        allow_rule = npm_endpoint.rules.add()
        allow_rule.allow.method = method
        allow_rule.allow.path = "/**"

    for path in _NPM_AUDIT_PATHS:
        allow_rule = npm_endpoint.rules.add()
        allow_rule.allow.method = "POST"
        allow_rule.allow.path = path

    npm_binary = npm_policy.binaries.add()
    npm_binary.path = _NPM_NODE_BINARY


def _add_browser_policy(
    spec: openshell_pb2.SandboxSpec,
) -> None:
    browser_policy = spec.policy.network_policies["browser_web"]
    browser_policy.name = "browser-web"

    for host, port in _browser_endpoints():
        endpoint = browser_policy.endpoints.add()
        endpoint.host = host
        endpoint.port = port

    browser_binary = browser_policy.binaries.add()
    browser_binary.path = _BROWSER_BINARY


def build_sandbox_spec(
    workspace_id: str | None = None,
    profile: str = "default",
) -> openshell_pb2.SandboxSpec:
    """
    Build the OpenShell sandbox specification.

    workspace_id is an optional application-level host workspace capability.

    When workspace_id is provided, the authorized host workspace volume is
    mounted into the sandbox.

    When workspace_id is None, no host filesystem resource is mounted and the
    sandbox's own filesystem becomes the application workspace.
    """
    profile = validate_profile(profile)

    cpu = validate_cpu(DEFAULT_CPU)
    memory = validate_memory(DEFAULT_MEMORY)

    grant: dict[str, object] | None = None

    if workspace_id is not None:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("host_workspace_id must not be empty.")

        grant = get_workspace_grant(workspace_id)

    spec = openshell_pb2.SandboxSpec()

    if profile == "browser":
        spec.template.image = BROWSER_SANDBOX_IMAGE
        spec.command.extend(
            [
                "/usr/bin/dumb-init",
                "--",
                "/usr/local/bin/browser-runtime",
            ]
        )
    else:
        spec.template.image = SANDBOX_IMAGE
        spec.command.extend(
            [
                "sleep",
                "infinity",
            ]
        )

    spec.template.resources.update(
        {
            "limits": {
                "cpu": cpu,
                "memory": memory,
            }
        }
    )

    if grant is not None:
        volume_name = grant["volume_name"]
        target = grant["target"]
        read_only = grant["read_only"]

        if not isinstance(volume_name, str) or not volume_name.strip():
            raise ValueError(
                f"Workspace grant '{workspace_id}' has no valid volume name."
            )

        if not isinstance(target, str) or not target.strip():
            raise ValueError(
                f"Workspace grant '{workspace_id}' has no valid mount target."
            )

        if not isinstance(read_only, bool):
            raise ValueError(
                f"Workspace grant '{workspace_id}' has an invalid read_only value."
            )

        spec.template.driver_config.update(
            {
                "docker": {
                    "mounts": [
                        {
                            "type": "volume",
                            "source": volume_name,
                            "target": target,
                            "read_only": read_only,
                        },
                    ],
                },
            }
        )

    spec.policy.version = 1
    spec.policy.filesystem.include_workdir = True

    spec.policy.filesystem.read_only.extend(
        [
            "/bin",
            "/usr",
            "/lib",
            "/proc",
            "/dev/urandom",
            "/etc",
            "/var/log",
        ]
    )

    spec.policy.filesystem.read_write.extend(
        [
            "/tmp",
            "/dev/null",
            SANDBOX_WORKSPACE_ROOT,
        ]
    )

    if profile == "browser":
        spec.policy.filesystem.read_only.append("/opt/chrome")
        spec.policy.filesystem.read_write.append("/home/chrome")
        _add_browser_policy(spec)
    else:
        _add_npm_policy(spec)

    spec.policy.landlock.compatibility = "hard_requirement"

    return spec
