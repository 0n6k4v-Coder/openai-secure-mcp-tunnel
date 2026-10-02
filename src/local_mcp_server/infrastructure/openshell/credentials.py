from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
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
    raw = os.environ.get(GATEWAY_ENDPOINT_ENV, DEFAULT_GATEWAY_ENDPOINT).strip()

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
        raise CredentialError(
            "OpenShell CLI gateway endpoint must contain a hostname."
        )

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

    message = (
        f"OpenShell credential {operation} failed with exit code {return_code}."
    )

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


def list_credentials() -> int:
    return _run_passthrough(_openshell_command("provider", "list"))


def show_credential(name: str) -> int:
    name = _validate_provider_name(name)
    return _run_passthrough(_openshell_command("provider", "get", name))


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
