from __future__ import annotations

import os
import re

from openshell._proto import openshell_pb2

from ..workspace import resolve_workspace_grant


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

_SANDBOX_NAME = re.compile(
    r"^[a-z0-9][a-z0-9-]{0,62}$"
)

_CPU_QUANTITY = re.compile(
    r"^(?:\d+(?:\.\d+)?|\d+m)$"
)

_MEMORY_QUANTITY = re.compile(
    r"^\d+(?:\.\d+)?(?:Ki|Mi|Gi|Ti|Pi|Ei|K|M|G|T|P|E)$"
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
            "CPU must be a Kubernetes-style quantity such as "
            "500m, 1, or 2.5"
        )

    return value


def validate_memory(value: str) -> str:
    if (
        not isinstance(value, str)
        or not _MEMORY_QUANTITY.fullmatch(value)
    ):
        raise ValueError(
            "memory must be a quantity such as "
            "512Mi, 4Gi, or 8G"
        )

    return value


def validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ValueError(
            "command must not be empty"
        )

    if len(command.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise ValueError(
            f"command exceeds {MAX_COMMAND_BYTES} bytes"
        )

    return command


def build_sandbox_spec(
    workspace_id: str,
) -> openshell_pb2.SandboxSpec:
    """
    Build the OpenShell sandbox specification.

    The host path is never supplied directly by the model. It is resolved
    through an opaque, previously authorized workspace capability into a
    system-managed Docker volume name.
    """
    cpu = validate_cpu(DEFAULT_CPU)
    memory = validate_memory(DEFAULT_MEMORY)

    volume_name = resolve_workspace_grant(
        workspace_id
    )

    spec = openshell_pb2.SandboxSpec()

    spec.template.image = SANDBOX_IMAGE

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
                        "target": "/workspace/project",
                        "read_only": False,
                    }
                ]
            }
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
            "/workspace/project",
        ]
    )

    spec.policy.landlock.compatibility = "hard_requirement"

    return spec