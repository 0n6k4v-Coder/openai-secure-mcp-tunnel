from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from ..manager import (
    PackageManagerError,
    PackageResult,
    _confirm,
    _lock_path,
    _manifest_path,
    _read_json,
    _safe_managed_dir,
    _sanitize_diagnostic,
    _sandbox_path_preflight,
)

_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_SPECIFIER = re.compile(
    r"^(?:(?:===|==|!=|~=|>=|<=|>|<)"
    r"[A-Za-z0-9.*+!_-][A-Za-z0-9.*+!_.,<>=~-]*)?$"
)
_NAME_AND_SPECIFIER = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"(?P<specifier>(?:(?:===|==|!=|~=|>=|<=|>|<).+)?)$"
)
_LOCK_HEADER = "# mcpctl-manifest-sha256: "
_LOCK_BODY_HEADER = "# mcpctl-lock-sha256: "
_INSTALL_MARKER = {
    "schema_version": 1,
    "managed_by": "mcpctl",
    "ecosystem": "python",
}


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _manifest_digest(manifest: dict[str, object]) -> str:
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_text(path: Path, content: str) -> None:
    _safe_managed_dir(path.parent, create=True)
    if path.is_symlink():
        raise PackageManagerError(f"Refusing to replace symlink: {path}")

    fd, temp_name = tempfile.mkstemp(prefix=".package.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            if not content.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise PackageManagerError(
            f"Could not atomically write {path}: {type(exc).__name__}"
        ) from exc
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class PythonUvAdapter:
    """Manage Python dependencies with uv and an isolated virtual environment."""

    ecosystem_id = "python"
    package_manager = "uv"
    manifest_name = "requirements.json"
    lock_name = "requirements.lock"
    runtime_argv = ("uv", "--version")
    install_relative_path = ".mcp-managed-packages/python"
    network_profile = "default"

    def validate_spec(self, package_spec: str) -> tuple[str, str]:
        if (
            not isinstance(package_spec, str)
            or not package_spec
            or package_spec.strip() != package_spec
            or any(char in package_spec for char in "\r\n\x00")
        ):
            raise ValueError(
                "Python package spec must be a package name and optional version specifier."
            )
        if any(token in package_spec for token in ("://", "git+", "file:", "/", "\\", "@", ";")):
            raise ValueError(
                "URL, VCS, local-path, direct-reference, extras, and environment-marker specs are not allowed."
            )

        match = _NAME_AND_SPECIFIER.fullmatch(package_spec)
        if match is None:
            raise ValueError("Invalid Python package specification.")

        name = match.group("name")
        specifier = match.group("specifier")
        if not _PACKAGE_NAME.fullmatch(name) or not _SPECIFIER.fullmatch(specifier):
            raise ValueError("Invalid Python package name or version specifier.")

        return _normalized_name(name), specifier or "*"

    def base_manifest(self, sandbox: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "name": f"mcp-sandbox-{sandbox}",
            "private": True,
            "dependencies": {},
        }

    def dependencies(self, manifest: dict[str, object]) -> dict[str, str]:
        dependencies = manifest.get("dependencies", {})
        if not isinstance(dependencies, dict) or not all(
            isinstance(name, str) and isinstance(specifier, str)
            for name, specifier in dependencies.items()
        ):
            raise PackageManagerError(
                "Python manifest dependencies must be a string-to-string object."
            )
        return dict(dependencies)

    def validate_manifest(self, manifest: object) -> dict[str, object]:
        if not isinstance(manifest, dict):
            raise PackageManagerError("Python manifest must be a JSON object.")
        if manifest.get("schema_version") != 1 or manifest.get("private") is not True:
            raise PackageManagerError(
                "Managed Python manifest has an unsupported schema."
            )
        if not isinstance(manifest.get("name"), str):
            raise PackageManagerError("Managed Python manifest requires a name.")

        dependencies = self.dependencies(manifest)
        for name, specifier in dependencies.items():
            try:
                package_spec = name if specifier == "*" else f"{name}{specifier}"
                parsed_name, parsed_specifier = self.validate_spec(package_spec)
            except ValueError as exc:
                raise PackageManagerError(
                    "Python manifest contains an invalid package specification."
                ) from exc
            if parsed_name != name or parsed_specifier != specifier:
                raise PackageManagerError(
                    "Python manifest contains a non-normalized or invalid package specification."
                )
        return dict(manifest)

    def lock_status(
        self, sandbox: str, manifest_path: Path, lock_path: Path
    ) -> str:
        if manifest_path.is_symlink() or lock_path.is_symlink():
            return "INVALID"
        if not manifest_path.exists():
            return "NONE"
        if not lock_path.exists():
            return "OUT OF DATE"
        try:
            manifest = self.validate_manifest(_read_json(manifest_path))
            lines = lock_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if len(lines) < 2:
                return "INVALID"
            if lines[0].rstrip("\r\n") != _LOCK_HEADER + _manifest_digest(manifest):
                return "OUT OF DATE"
            if not lines[1].startswith(_LOCK_BODY_HEADER):
                return "INVALID"
            lock_body = "".join(lines[2:])
            expected_body_digest = _LOCK_BODY_HEADER + hashlib.sha256(
                lock_body.encode("utf-8")
            ).hexdigest()
            if lines[1].rstrip("\r\n") != expected_body_digest:
                return "INVALID"
            return "UP TO DATE"
        except (OSError, PackageManagerError, ValueError):
            return "INVALID"

    def resolved_versions(
        self, sandbox: str, dependencies: dict[str, str]
    ) -> dict[str, str]:
        lock_path = _lock_path(sandbox, self.ecosystem_id)
        if self.lock_status(
            sandbox, _manifest_path(sandbox, self.ecosystem_id), lock_path
        ) != "UP TO DATE":
            return {}
        try:
            lines = lock_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}

        wanted = {_normalized_name(name): name for name in dependencies}
        resolved: dict[str, str] = {}
        for line in lines[2:]:
            match = re.match(r"^([A-Za-z0-9_.-]+)==([^\\\s;]+)", line.strip())
            if match is None:
                continue
            normalized = _normalized_name(match.group(1))
            if normalized in wanted:
                resolved[wanted[normalized]] = match.group(2)
        return resolved

    def lock(self, sandbox: str) -> PackageResult:
        from ...infrastructure.openshell.sandbox import (
            execute_sandbox_argv,
            sandbox_status,
        )
        from ...infrastructure.openshell.sandbox_files import (
            create_sandbox_workspace_directory,
            delete_sandbox_workspace_directory,
            read_sandbox_workspace_text_file,
            write_sandbox_file,
        )

        manifest_path = _manifest_path(sandbox, self.ecosystem_id)
        lock_path = _lock_path(sandbox, self.ecosystem_id)
        if not manifest_path.exists():
            raise PackageManagerError(
                f"Package configuration was not found: {manifest_path}",
                exit_code=3,
            )
        manifest = self.validate_manifest(_read_json(manifest_path))
        metadata = json.loads(sandbox_status(sandbox))
        if (
            not isinstance(metadata, dict)
            or metadata.get("profile", "default") != self.network_profile
        ):
            raise PackageManagerError(
                "Python lock requires a default-profile sandbox with the approved Python package-index policy.",
                exit_code=4,
            )

        dependencies = self.dependencies(manifest)
        if not dependencies:
            _atomic_text(
                lock_path,
                _LOCK_HEADER
                + _manifest_digest(manifest)
                + "\n"
                + _LOCK_BODY_HEADER
                + hashlib.sha256(b"").hexdigest()
                + "\n",
            )
            return PackageResult(
                "lock",
                sandbox,
                self.ecosystem_id,
                "Empty Python dependency set locked; lockfile is UP TO DATE.",
                manifest_path,
                lock_path,
                "locked",
            )

        stage = f".mcp-python-lock-{sandbox}"
        _sandbox_path_preflight(sandbox, stage, allow_existing=False)
        create_sandbox_workspace_directory(sandbox, stage)
        cleanup_error: Exception | None = None
        try:
            requirements = "".join(
                f"{name}\n"
                if specifier == "*"
                else f"{name}{specifier}\n"
                for name, specifier in sorted(self.dependencies(manifest).items())
            )
            write_sandbox_file(
                sandbox, f"{stage}/requirements.in", requirements, overwrite=False
            )
            result = execute_sandbox_argv(
                sandbox,
                [
                    "uv", "pip", "compile",
                    "--generate-hashes",
                    "--only-binary", ":all:",
                    "--output-file",
                    f"/workspace/project/{stage}/requirements.lock",
                    f"/workspace/project/{stage}/requirements.in",
                ],
                timeout_seconds=180,
            )
            if int(result.get("return_code", 1)) != 0:
                detail = _sanitize_diagnostic(
                    str(
                        result.get("stderr")
                        or result.get("stdout")
                        or "uv resolution failed"
                    ).strip()
                )
                raise PackageManagerError(
                    "Python dependency resolution failed; existing lockfile preserved. "
                    f"Reason: {detail}"
                )

            lock_text = read_sandbox_workspace_text_file(
                sandbox, f"{stage}/requirements.lock"
            )
            if not lock_text.strip():
                raise PackageManagerError(
                    "uv produced an empty requirements lockfile; existing lockfile preserved."
                )
            lock_body = lock_text if lock_text.endswith("\n") else lock_text + "\n"
            _atomic_text(
                lock_path,
                _LOCK_HEADER
                + _manifest_digest(manifest)
                + "\n"
                + _LOCK_BODY_HEADER
                + hashlib.sha256(lock_body.encode("utf-8")).hexdigest()
                + "\n"
                + lock_body,
            )
            return PackageResult(
                "lock",
                sandbox,
                self.ecosystem_id,
                "Python dependencies resolved; lockfile is UP TO DATE.",
                manifest_path,
                lock_path,
                "locked",
            )
        finally:
            try:
                delete_sandbox_workspace_directory(sandbox, stage)
            except Exception as exc:
                cleanup_error = exc
            if cleanup_error is not None:
                raise PackageManagerError(
                    f"Python lock operation left temporary staging state at {stage}; "
                    f"cleanup failed: {type(cleanup_error).__name__}. Inspect the sandbox before retrying."
                ) from cleanup_error

    def install(
        self, sandbox: str, *, confirmed: bool, no_input: bool
    ) -> PackageResult:
        from ...infrastructure.openshell.sandbox import (
            execute_sandbox_argv,
            sandbox_status,
        )
        from ...infrastructure.openshell.sandbox_files import (
            create_sandbox_workspace_directory,
            read_sandbox_workspace_text_file,
            write_sandbox_file,
        )

        manifest_path = _manifest_path(sandbox, self.ecosystem_id)
        lock_path = _lock_path(sandbox, self.ecosystem_id)
        if not manifest_path.exists():
            raise PackageManagerError(
                f"Package configuration was not found: {manifest_path}",
                exit_code=3,
            )
        if self.lock_status(sandbox, manifest_path, lock_path) != "UP TO DATE":
            raise PackageManagerError(
                f"Python lockfile is missing or stale: {lock_path}. Run the lock command first.",
                exit_code=3,
            )
        _confirm(
            "package installation",
            sandbox,
            self.ecosystem_id,
            confirmed=confirmed,
            no_input=no_input,
        )
        self.validate_manifest(_read_json(manifest_path))
        lock_text = lock_path.read_text(encoding="utf-8")
        lock_lines = lock_text.splitlines(keepends=True)
        uv_lock_text = "".join(lock_lines[2:])

        metadata = json.loads(sandbox_status(sandbox))
        if (
            not isinstance(metadata, dict)
            or metadata.get("profile", "default") != self.network_profile
        ):
            raise PackageManagerError(
                "Python install requires a default-profile sandbox with the approved Python package-index policy.",
                exit_code=4,
            )

        install_root = self.install_relative_path
        marker_path = f"{install_root}/.mcp-managed.json"
        lock_relative = f"{install_root}/requirements.lock"
        venv_relative = f"{install_root}/.venv"
        venv_python = f"/workspace/project/{venv_relative}/bin/python"
        _sandbox_path_preflight(sandbox, install_root, allow_existing=True)
        _sandbox_path_preflight(
            sandbox, marker_path, allow_existing=True, directory=False
        )
        _sandbox_path_preflight(
            sandbox, lock_relative, allow_existing=True, directory=False
        )
        _sandbox_path_preflight(sandbox, venv_relative, allow_existing=True)

        created_root = False
        try:
            create_sandbox_workspace_directory(sandbox, install_root)
            created_root = True
        except Exception as exc:
            try:
                marker = json.loads(
                    read_sandbox_workspace_text_file(sandbox, marker_path)
                )
            except Exception:
                raise PackageManagerError(
                    f"Install path already exists and is not verified as managed: {install_root}"
                ) from exc
            if marker != _INSTALL_MARKER:
                raise PackageManagerError(
                    f"Install path marker is invalid; refusing to modify {install_root}."
                )

        try:
            if created_root:
                write_sandbox_file(
                    sandbox,
                    marker_path,
                    json.dumps(_INSTALL_MARKER, sort_keys=True) + "\n",
                    overwrite=False,
                )
            write_sandbox_file(
                sandbox, lock_relative, uv_lock_text, overwrite=True
            )

            venv_result = execute_sandbox_argv(
                sandbox,
                ["uv", "venv", "--python", "python", f"/workspace/project/{venv_relative}"],
                timeout_seconds=60,
            )
            if int(venv_result.get("return_code", 1)) != 0:
                detail = _sanitize_diagnostic(
                    str(
                        venv_result.get("stderr")
                        or venv_result.get("stdout")
                        or "uv venv failed"
                    ).strip()
                )
                raise PackageManagerError(
                    f"Python virtual environment creation failed. Reason: {detail}"
                )

            install_result = execute_sandbox_argv(
                sandbox,
                [
                    "uv", "pip", "sync",
                    "--allow-empty-requirements",
                    "--only-binary", ":all:",
                    "--require-hashes",
                    "--python", venv_python,
                    f"/workspace/project/{lock_relative}",
                ],
                timeout_seconds=300,
            )
            if int(install_result.get("return_code", 1)) != 0:
                detail = _sanitize_diagnostic(
                    str(
                        install_result.get("stderr")
                        or install_result.get("stdout")
                        or "uv pip sync failed"
                    ).strip()
                )
                raise PackageManagerError(
                    f"Python package installation failed. Reason: {detail}"
                )

            status = self.verify_installation(sandbox)
            if status != "INSTALLED":
                raise PackageManagerError(
                    f"uv completed but Python installation verification returned {status}."
                )
            return PackageResult(
                "install",
                sandbox,
                self.ecosystem_id,
                "Locked Python dependencies installed into the managed virtual environment and verified.",
                manifest_path,
                lock_path,
                "installed",
            )
        except PackageManagerError:
            raise
        except Exception as exc:
            raise PackageManagerError(
                "Python package installation failed; inspect sandbox state. "
                f"Reason: {type(exc).__name__}: {exc}"
            ) from exc

    def verify_installation(self, sandbox: str) -> str:
        from ...infrastructure.openshell.sandbox import (
            execute_sandbox_argv,
            sandbox_status,
        )

        metadata = json.loads(sandbox_status(sandbox))
        profile = (
            metadata.get("profile", "default")
            if isinstance(metadata, dict)
            else "default"
        )
        if profile != self.network_profile:
            return "UNAVAILABLE"

        manifest_path = _manifest_path(sandbox, self.ecosystem_id)
        lock_path = _lock_path(sandbox, self.ecosystem_id)
        if self.lock_status(sandbox, manifest_path, lock_path) != "UP TO DATE":
            return "REQUIRES VERIFICATION"

        venv_python = (
            f"/workspace/project/{self.install_relative_path}/.venv/bin/python"
        )
        result = execute_sandbox_argv(
            sandbox,
            ["uv", "pip", "freeze", "--python", venv_python],
            timeout_seconds=30,
        )
        if int(result.get("return_code", 1)) != 0:
            return "NOT INSTALLED"

        actual: set[str] = set()
        output = result.get("stdout")
        if isinstance(output, str):
            for line in output.splitlines():
                if "==" in line:
                    name = line.split("==", 1)[0].strip()
                    actual.add(_normalized_name(name))

        manifest = self.validate_manifest(_read_json(manifest_path))
        expected = {
            _normalized_name(name)
            for name in self.dependencies(manifest)
        }
        return (
            "INSTALLED"
            if expected.issubset(actual)
            else ("PARTIAL" if actual else "NOT INSTALLED")
        )
