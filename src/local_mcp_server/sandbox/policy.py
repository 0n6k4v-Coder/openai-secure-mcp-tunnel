from __future__ import annotations

import os
import re

from openshell._proto import openshell_pb2

from ..workspace.repository import get_workspace_grant


SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE",
    "local-mcp-openshell-sandbox:1.0.0",
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

_SANDBOX_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

_CPU_QUANTITY = re.compile(r"^(?:\d+(?:\.\d+)?|\d+m)$")

_MEMORY_QUANTITY = re.compile(
    r"^\d+(?:\.\d+)?(?:Ki|Mi|Gi|Ti|Pi|Ei|K|M|G|T|P|E)$"
)

_NPM_NODE_BINARY = "/usr/local/bin/node"
_NPM_REGISTRY_HOST = "registry.npmjs.org"
_NPM_REGISTRY_PORT = 443
_NPM_AUDIT_PATHS = (
    "/-/npm/v1/security/advisories/bulk",
    "/-/npm/v1/security/audits/quick",
)

_BROWSER_NODE_BINARY = "/usr/local/bin/node"
_BROWSER_HOST = os.environ.get(
    "BROWSER_ENDPOINT_HOST",
    "host.openshell.internal",
)
_BROWSER_PORT = int(
    os.environ.get(
        "BROWSER_ENDPOINT_PORT",
        "9223",
    )
)


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not _SANDBOX_NAME.fullmatch(name):
        raise ValueError(
            "sandbox name must contain only lowercase letters, digits, "
            "and hyphens, start with a letter or digit, and be at most "
            "63 characters"
        )

    return name


def validate_cpu(value: str) -> str:
    if not isinstance(value, str) or not _CPU_QUANTITY.fullmatch(value):
        raise ValueError(
            "CPU must be a Kubernetes-style quantity such as 500m, 1, or 2.5"
        )

    return value


def validate_memory(value: str) -> str:
    if not isinstance(value, str) or not _MEMORY_QUANTITY.fullmatch(value):
        raise ValueError(
            "memory must be a quantity such as 512Mi, 4Gi, or 8G"
        )

    return value


def validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must not be empty")

    if len(command.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise ValueError(f"command exceeds {MAX_COMMAND_BYTES} bytes")

    return command


def build_sandbox_spec(
    workspace_id: str,
) -> openshell_pb2.SandboxSpec:
    """
    Build the OpenShell sandbox specification.

    The host path is never supplied directly by the model. It is resolved
    through an opaque, previously authorized workspace capability into the
    system-managed Docker volume, mount target, and access mode stored in
    the grant database.
    """
    cpu = validate_cpu(DEFAULT_CPU)
    memory = validate_memory(DEFAULT_MEMORY)

    grant = get_workspace_grant(workspace_id)

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

    spec = openshell_pb2.SandboxSpec()

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
            target,
        ]
    )

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

    browser_policy = spec.policy.network_policies["browser_cdp"]
    browser_policy.name = "browser-cdp"

    browser_endpoint = browser_policy.endpoints.add()
    browser_endpoint.host = _BROWSER_HOST
    browser_endpoint.port = _BROWSER_PORT
    browser_endpoint.protocol = "tcp"

    browser_binary = browser_policy.binaries.add()
    browser_binary.path = _BROWSER_NODE_BINARY

    spec.policy.landlock.compatibility = "hard_requirement"

    return spec