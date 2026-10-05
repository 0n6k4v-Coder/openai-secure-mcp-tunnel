from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


OPEN_SHELL_GATEWAY_IMAGE = "ghcr.io/nvidia/openshell/gateway:" + os.environ.get(
    "OPENSHELL_IMAGE_TAG", "latest"
)

OPEN_SHELL_CLI_GATEWAY_NAME = "local"

EXPECTED_FILES = (
    Path("ca.crt"),
    Path("server/tls.crt"),
    Path("server/tls.key"),
    Path("client/ca.crt"),
    Path("client/tls.crt"),
    Path("client/tls.key"),
    Path("jwt/signing.pem"),
    Path("jwt/public.pem"),
    Path("jwt/kid"),
)

DIRECTORY_MODES = 0o700
FILE_MODE = 0o600
CLI_CERT_MODE = 0o644
CLI_KEY_MODE = 0o600


class OpenShellTLSStatusError(RuntimeError):
    """Raised when OpenShell TLS lifecycle management cannot proceed."""


@dataclass(frozen=True)
class TLSStatus:
    root: Path
    complete: bool
    missing: tuple[Path, ...]
    insecure_paths: tuple[Path, ...]


def _xdg_state_home() -> Path:
    value = os.environ.get("XDG_STATE_HOME")

    if value:
        candidate = Path(value).expanduser()

        if candidate.is_absolute():
            return candidate

    return Path.home() / ".local" / "state"


def _xdg_config_home() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME")

    if value:
        candidate = Path(value).expanduser()

        if candidate.is_absolute():
            return candidate

    return Path.home() / ".config"


def tls_root() -> Path:
    return _xdg_state_home() / "local-mcp-server" / "openshell" / "tls"


def _openshell_cli_mtls_root() -> Path:
    return (
        _xdg_config_home()
        / "openshell"
        / "gateways"
        / OPEN_SHELL_CLI_GATEWAY_NAME
        / "mtls"
    )


def _required_paths(root: Path) -> tuple[Path, ...]:
    return tuple(root / relative_path for relative_path in EXPECTED_FILES)


def _insecure_paths(root: Path) -> tuple[Path, ...]:
    insecure: list[Path] = []

    for relative_path in EXPECTED_FILES:
        path = root / relative_path

        if not path.exists():
            continue

        if path.is_dir():
            insecure.append(path)
            continue

        mode = stat.S_IMODE(path.stat().st_mode)

        if mode & 0o077:
            insecure.append(path)

    for directory in (
        root,
        root / "server",
        root / "client",
        root / "jwt",
    ):
        if not directory.exists():
            continue

        mode = stat.S_IMODE(directory.stat().st_mode)

        if mode & 0o077:
            insecure.append(directory)

    return tuple(insecure)


def get_status() -> TLSStatus:
    root = tls_root()
    required_paths = _required_paths(root)

    missing = tuple(path for path in required_paths if not path.is_file())

    insecure_paths = _insecure_paths(root)

    return TLSStatus(
        root=root,
        complete=not missing and not insecure_paths,
        missing=missing,
        insecure_paths=insecure_paths,
    )


def _ensure_directory(path: Path) -> None:
    path.mkdir(
        parents=True,
        exist_ok=True,
        mode=DIRECTORY_MODES,
    )
    os.chmod(path, DIRECTORY_MODES)


def _ensure_parent_directories(root: Path) -> None:
    _ensure_directory(root)
    _ensure_directory(root / "server")
    _ensure_directory(root / "client")
    _ensure_directory(root / "jwt")


def _set_private_permissions(root: Path) -> None:
    for relative_path in EXPECTED_FILES:
        path = root / relative_path

        if path.is_file():
            os.chmod(path, FILE_MODE)


def _prepare_client_ca(root: Path) -> None:
    ca_path = root / "ca.crt"
    client_ca_path = root / "client" / "ca.crt"

    if not ca_path.is_file():
        raise OpenShellTLSStatusError(
            "OpenShell TLS generation did not produce ca.crt."
        )

    shutil.copy2(
        ca_path,
        client_ca_path,
    )


def _atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    mode: int,
) -> None:
    _ensure_directory(path.parent)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )

    temporary_path = Path(temporary_name)

    try:
        os.chmod(temporary_path, mode)

        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            path,
        )

        os.chmod(path, mode)

    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass

        raise


def _sync_openshell_cli_bundle(root: Path) -> None:
    source_ca = root / "ca.crt"
    source_cert = root / "client" / "tls.crt"
    source_key = root / "client" / "tls.key"

    required_sources = (
        source_ca,
        source_cert,
        source_key,
    )

    missing = [
        str(path.relative_to(root)) for path in required_sources if not path.is_file()
    ]

    if missing:
        raise OpenShellTLSStatusError(
            "Cannot synchronize the OpenShell CLI mTLS bundle because "
            "required TLS files are missing: " + ", ".join(missing)
        )

    target_root = _openshell_cli_mtls_root()

    try:
        _ensure_directory(target_root)

        _atomic_write_bytes(
            target_root / "ca.crt",
            source_ca.read_bytes(),
            mode=CLI_CERT_MODE,
        )

        _atomic_write_bytes(
            target_root / "tls.crt",
            source_cert.read_bytes(),
            mode=CLI_CERT_MODE,
        )

        _atomic_write_bytes(
            target_root / "tls.key",
            source_key.read_bytes(),
            mode=CLI_KEY_MODE,
        )

    except OpenShellTLSStatusError:
        raise

    except OSError as exc:
        raise OpenShellTLSStatusError(
            f"Unable to synchronize the OpenShell CLI mTLS bundle: {exc}"
        ) from exc


def _run_generate_certs(root: Path) -> None:
    parent = root.parent

    config_home = _xdg_config_home()

    _ensure_directory(parent)
    _ensure_directory(config_home)

    with tempfile.TemporaryDirectory(
        prefix=".openshell-tls-",
        dir=parent,
    ) as temporary:
        temporary_root = Path(temporary)

        command = [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            (f"{parent}:/home/openshell/.local/state/local-mcp-server/openshell"),
            "-v",
            f"{config_home}:/home/openshell/.config",
            OPEN_SHELL_GATEWAY_IMAGE,
            "generate-certs",
            "--output-dir",
            (
                "/home/openshell/.local/state/"
                "local-mcp-server/openshell/" + temporary_root.name
            ),
            "--server-san",
            "host.openshell.internal",
            "--server-san",
            "openshell-gateway",
        ]

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )

        except FileNotFoundError as exc:
            raise OpenShellTLSStatusError(
                "Docker is required to generate OpenShell TLS material."
            ) from exc

        except subprocess.TimeoutExpired as exc:
            raise OpenShellTLSStatusError(
                "OpenShell TLS generation timed out."
            ) from exc

        except OSError as exc:
            raise OpenShellTLSStatusError(
                f"Failed to execute Docker: {type(exc).__name__}: {exc}"
            ) from exc

        if completed.returncode != 0:
            diagnostic = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or "OpenShell returned no diagnostic output."
            )

            raise OpenShellTLSStatusError(
                f"OpenShell TLS generation failed: {diagnostic}"
            )

        generated_paths = (
            temporary_root / "ca.crt",
            temporary_root / "server/tls.crt",
            temporary_root / "server/tls.key",
            temporary_root / "client/tls.crt",
            temporary_root / "client/tls.key",
            temporary_root / "jwt/signing.pem",
            temporary_root / "jwt/public.pem",
            temporary_root / "jwt/kid",
        )

        missing = [
            str(path.relative_to(temporary_root))
            for path in generated_paths
            if not path.is_file()
        ]

        if missing:
            raise OpenShellTLSStatusError(
                "OpenShell TLS generation completed without the required "
                f"files: {', '.join(missing)}"
            )

        _prepare_client_ca(temporary_root)

        if root.exists():
            shutil.rmtree(root)

        shutil.move(
            str(temporary_root),
            str(root),
        )


def _rebuild() -> TLSStatus:
    root = tls_root()

    if root.exists():
        shutil.rmtree(root)

    _ensure_parent_directories(root)

    _run_generate_certs(root)

    _ensure_parent_directories(root)
    _set_private_permissions(root)

    _sync_openshell_cli_bundle(root)

    final = get_status()

    if not final.complete:
        details: list[str] = []

        if final.missing:
            details.append(
                "missing: "
                + ", ".join(str(path.relative_to(final.root)) for path in final.missing)
            )

        if final.insecure_paths:
            details.append(
                "insecure permissions: "
                + ", ".join(
                    str(path.relative_to(final.root)) for path in final.insecure_paths
                )
            )

        raise OpenShellTLSStatusError(
            "OpenShell TLS setup did not produce a healthy bundle"
            + (f" ({'; '.join(details)})" if details else ".")
        )

    return final


def setup() -> TLSStatus:
    current = get_status()

    if current.complete:
        _sync_openshell_cli_bundle(current.root)
        return current

    return _rebuild()


def repair() -> TLSStatus:
    current = get_status()

    if current.complete:
        _sync_openshell_cli_bundle(current.root)
        return current

    return _rebuild()
