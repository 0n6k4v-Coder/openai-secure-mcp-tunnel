from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import urlparse


DEFAULT_GATEWAY_ENDPOINT = "https://127.0.0.1:8080"
GATEWAY_ENDPOINT_ENV = "OPENSHELL_CLI_GATEWAY"

_COMMAND_TIMEOUT_SECONDS = 60

_PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_PROVIDER_TYPE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_CREDENTIAL_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class CredentialError(RuntimeError):
    """Raised when a host-side credential operation fails."""


def _command_exists(command: str) -> None:
    if shutil.which(command) is None:
        raise CredentialError(
            f"Required command '{command}' is not installed or is not on PATH."
        )


def _gateway_endpoint() -> str:
    from ...runtime.context import get_runtime_context
    context = get_runtime_context()
    default_endpoint = DEFAULT_GATEWAY_ENDPOINT
    if not context.is_default:
        default_endpoint = os.environ.get("OPENSHELL_RUNTIME_GATEWAY", f"https://127.0.0.1:{context.profile.openshell_port}")
    raw = os.environ.get(GATEWAY_ENDPOINT_ENV, default_endpoint).strip()

    if not raw:
        raise CredentialError(f"{GATEWAY_ENDPOINT_ENV} must not be empty.")

    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlparse(raw)

    if parsed.scheme not in {"http", "https"}:
        raise CredentialError(
            "OpenShell CLI gateway endpoint must use http:// or https://."
        )

    if not parsed.hostname:
        raise CredentialError("OpenShell CLI gateway endpoint must contain a hostname.")

    if parsed.username or parsed.password:
        raise CredentialError(
            "OpenShell CLI gateway endpoint must not contain credentials."
        )

    if parsed.fragment:
        raise CredentialError(
            "OpenShell CLI gateway endpoint must not contain a URL fragment."
        )

    return raw


def _validate_provider_name(name: str) -> str:
    if not isinstance(name, str) or not _PROVIDER_NAME.fullmatch(name):
        raise ValueError(
            "credential name must contain only lowercase letters, digits, "
            "and hyphens, start with a letter or digit, and be at most "
            "63 characters"
        )
    return name


def _validate_provider_type(provider_type: str) -> str:
    if not isinstance(provider_type, str) or not _PROVIDER_TYPE.fullmatch(
        provider_type
    ):
        raise ValueError(
            "credential type must contain only lowercase letters, digits, "
            "and hyphens, start with a letter or digit, and be at most "
            "63 characters"
        )
    return provider_type


def _validate_credential_key(key: str) -> str:
    if not isinstance(key, str) or not _CREDENTIAL_KEY.fullmatch(key):
        raise ValueError(
            "credential key must be an uppercase environment-style name "
            "containing only A-Z, digits, and underscores, and must start "
            "with A-Z"
        )
    return key


def _openshell_command(*args: str) -> list[str]:
    _command_exists("openshell")

    # For the default installation, target the registered gateway by name.
    # Passing --gateway-endpoint bypasses gateway metadata and makes OpenShell
    # look for mTLS files in a URL-derived directory (for example,
    # gateways/https___127.0.0.1_8080/mtls) instead of gateways/local/mtls.
    from ...runtime.context import get_runtime_context

    context = get_runtime_context()
    if context.is_default and GATEWAY_ENDPOINT_ENV not in os.environ:
        return ["openshell", "--gateway", "local", *args]

    # Named runtimes and explicit endpoint overrides use their dedicated
    # loopback endpoint.
    return ["openshell", "--gateway-endpoint", _gateway_endpoint(), *args]


def _run_capture(
    command: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            env=env,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise CredentialError(
            f"Required command '{command[0]}' is not installed or is not on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CredentialError("OpenShell credential operation timed out.") from exc


def _run_passthrough(command: Sequence[str]) -> int:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            shell=False,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise CredentialError(
            f"Required command '{command[0]}' is not installed or is not on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CredentialError("OpenShell credential operation timed out.") from exc
    return completed.returncode


def _raise_credential_operation_failure(
    operation: str,
    return_code: int,
    stderr: str = "",
) -> None:
    detail = stderr.strip()

    message = f"OpenShell credential {operation} failed with exit code {return_code}."

    if detail:
        message += f" {detail}"

    raise CredentialError(message)


def _read_secret(key: str) -> str:
    secret = getpass.getpass(f"Enter secret for {key}: ")

    if "\x00" in secret:
        raise ValueError("Credential value must not contain NUL bytes.")

    if not secret:
        raise ValueError("Credential value must not be empty.")

    confirmation = getpass.getpass(f"Confirm secret for {key}: ")

    if secret != confirmation:
        raise ValueError("Credential confirmation does not match.")

    return secret


def _credential_environment(key: str, secret: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment[key] = secret
    return environment


def create_credential(name: str, provider_type: str, credential_key: str) -> int:
    name = _validate_provider_name(name)
    provider_type = _validate_provider_type(provider_type)
    credential_key = _validate_credential_key(credential_key)
    secret = _read_secret(credential_key)

    result = _run_capture(
        _openshell_command(
            "provider",
            "create",
            "--name",
            name,
            "--type",
            provider_type,
            "--credential",
            credential_key,
        ),
        env=_credential_environment(credential_key, secret),
    )

    if result.returncode != 0:
        _raise_credential_operation_failure(
            "creation",
            result.returncode,
            result.stderr,
        )

    print(f"Credential created: {name}")
    print(f"Provider type:      {provider_type}")
    print(f"Credential key:     {credential_key}")
    return result.returncode


def update_credential(name: str, credential_key: str) -> int:
    name = _validate_provider_name(name)
    credential_key = _validate_credential_key(credential_key)
    secret = _read_secret(credential_key)

    result = _run_capture(
        _openshell_command(
            "provider",
            "update",
            name,
            "--credential",
            credential_key,
        ),
        env=_credential_environment(credential_key, secret),
    )

    if result.returncode != 0:
        _raise_credential_operation_failure("update", result.returncode)

    print(f"Credential updated: {name}")
    print(f"Credential key:     {credential_key}")
    return result.returncode


def list_sandbox_credentials(sandbox_name: str) -> list[dict[str, object]]:
    """List provider credentials attached to a specific sandbox."""
    sandbox_name = _validate_provider_name(sandbox_name)
    result = _run_capture(
        _openshell_command("sandbox", "provider", "list", sandbox_name, "-o", "json")
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            return data.get("providers", [])
    except Exception:
        return []
    return []


def _find_granted_sandboxes() -> dict[str, list[str]]:
    """Map credential/provider names to lists of sandboxes they are granted to."""
    granted: dict[str, list[str]] = {}
    sb_list_res = _run_capture(_openshell_command("sandbox", "list", "-o", "json"))
    if sb_list_res.returncode != 0:
        return granted

    try:
        sb_data = json.loads(sb_list_res.stdout)
        sandboxes = sb_data.get("sandboxes", []) if isinstance(sb_data, dict) else []
    except Exception:
        return granted

    for sb in sandboxes:
        if not isinstance(sb, dict):
            continue
        sb_name = sb.get("name")
        if not isinstance(sb_name, str) or not sb_name:
            continue

        prov_list_res = _run_capture(
            _openshell_command("sandbox", "provider", "list", sb_name, "-o", "json")
        )
        if prov_list_res.returncode != 0:
            continue

        try:
            prov_data = json.loads(prov_list_res.stdout)
            attached = prov_data.get("providers", []) if isinstance(prov_data, dict) else []
            for p in attached:
                if isinstance(p, dict):
                    p_name = p.get("name")
                    if isinstance(p_name, str) and p_name:
                        granted.setdefault(p_name, []).append(sb_name)
        except Exception:
            continue

    return granted


def list_credentials() -> int:
    providers_res = _run_capture(_openshell_command("provider", "list", "-o", "json"))
    if providers_res.returncode != 0:
        return _run_passthrough(_openshell_command("provider", "list"))

    try:
        providers_data = json.loads(providers_res.stdout)
        providers = providers_data.get("providers", []) if isinstance(providers_data, dict) else []
    except Exception:
        return _run_passthrough(_openshell_command("provider", "list"))

    if not providers:
        print("No credential providers found.")
        return 0

    granted_map = _find_granted_sandboxes()

    rows: list[list[str]] = []
    for p in providers:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name", ""))
        p_type = str(p.get("type", ""))
        cred_keys = str(len(p.get("credential_keys", [])))
        config_keys = str(len(p.get("config_keys", [])))
        sandboxes = ", ".join(sorted(granted_map.get(name, []))) or "<none>"
        rows.append([name, p_type, cred_keys, config_keys, sandboxes])

    # Print formatted table
    headers = ["NAME", "TYPE", "CREDENTIAL_KEYS", "CONFIG_KEYS", "GRANTED TO SANDBOXES"]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    separator_line = "  ".join("-" * widths[i] for i in range(len(headers)))
    print(header_line)
    print(separator_line)
    for row in rows:
        print("  ".join(val.ljust(widths[i]) for i, val in enumerate(row)))

    return 0


def show_credential(name: str) -> int:
    name = _validate_provider_name(name)
    result = _run_capture(_openshell_command("provider", "get", name))
    if result.returncode != 0:
        if result.stderr:
            sys.stderr.write(result.stderr)
        return result.returncode

    raw_output = result.stdout
    # Reduce empty line between "Provider:" and "  Id: ..."
    formatted = re.sub(r"^Provider:\s*\n\s*\n", "Provider:\n", raw_output.strip())
    print(formatted)
    print()

    granted_map = _find_granted_sandboxes()
    sandboxes = sorted(granted_map.get(name, []))
    print("Granted to sandboxes:")
    if sandboxes:
        for sb in sandboxes:
            print(f"  - {sb}")
    else:
        print("  <none>")
    return 0


def delete_credential(name: str) -> int:
    name = _validate_provider_name(name)
    return _run_passthrough(_openshell_command("provider", "delete", name))


def grant_credential(sandbox_name: str, credential_name: str) -> int:
    sandbox_name = _validate_provider_name(sandbox_name)
    credential_name = _validate_provider_name(credential_name)

    return _run_passthrough(
        _openshell_command(
            "sandbox",
            "provider",
            "attach",
            sandbox_name,
            credential_name,
            "--wait",
            "--timeout",
            "30",
        )
    )


def revoke_credential(sandbox_name: str, credential_name: str) -> int:
    sandbox_name = _validate_provider_name(sandbox_name)
    credential_name = _validate_provider_name(credential_name)

    return _run_passthrough(
        _openshell_command(
            "sandbox",
            "provider",
            "detach",
            sandbox_name,
            credential_name,
            "--wait",
            "--timeout",
            "30",
        )
    )
