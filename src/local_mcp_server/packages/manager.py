from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config.paths import app_state_root
from ..sandbox.policy import validate_name


class PackageManagerError(RuntimeError):
    """A package operation failed without claiming unverified state."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class PackageResult:
    operation: str
    sandbox: str
    ecosystem: str
    message: str
    manifest: Path | None = None
    lockfile: Path | None = None
    status: str = "configured"


class EcosystemAdapter(Protocol):
    ecosystem_id: str
    package_manager: str
    manifest_name: str
    lock_name: str
    runtime_argv: tuple[str, ...]
    install_relative_path: str
    network_profile: str

    def validate_spec(self, package_spec: str) -> tuple[str, str]: ...
    def base_manifest(self, sandbox: str) -> dict[str, object]: ...
    def dependencies(self, manifest: dict[str, object]) -> dict[str, str]: ...
    def validate_manifest(self, manifest: object) -> dict[str, object]: ...
    def lock_status(self, sandbox: str, manifest_path: Path, lock_path: Path) -> str: ...
    def resolved_versions(self, sandbox: str, dependencies: dict[str, str]) -> dict[str, str]: ...
    def lock(self, sandbox: str) -> PackageResult: ...
    def install(self, sandbox: str, *, confirmed: bool, no_input: bool) -> PackageResult: ...
    def verify_installation(self, sandbox: str) -> str: ...


class NpmAdapter:
    ecosystem_id = "npm"
    package_manager = "npm"
    manifest_name = "package.json"
    lock_name = "package-lock.json"
    runtime_argv = ("node", "--version")
    install_relative_path = ".mcp-managed-packages/npm"
    network_profile = "default"

    _package_name = re.compile(
        r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$"
    )
    _version_spec = re.compile(r"^[A-Za-z0-9*^~<>=|.+ -]+$")

    def validate_spec(self, package_spec: str) -> tuple[str, str]:
        if not isinstance(package_spec, str) or not package_spec or package_spec.strip() != package_spec:
            raise ValueError("Package spec must be a non-empty package name and optional version range.")
        if package_spec.startswith((".", "/", "git+", "http:", "https:", "file:")) or "://" in package_spec:
            raise ValueError("URL, Git, and local-path package specs are not allowed.")
        if package_spec.startswith("@"):
            slash = package_spec.find("/")
            if slash < 2:
                raise ValueError("Scoped package specs must use @scope/name[@version].")
            at = package_spec.find("@", slash)
        else:
            at = package_spec.find("@")
        name = package_spec if at < 0 else package_spec[:at]
        version = "*" if at < 0 else package_spec[at + 1:]
        if not self._package_name.fullmatch(name):
            raise ValueError("Invalid npm package name.")
        if not version or not self._version_spec.fullmatch(version):
            raise ValueError("Invalid npm version range.")
        return name, version

    def base_manifest(self, sandbox: str) -> dict[str, object]:
        return {"name": f"mcp-sandbox-{sandbox}", "version": "1.0.0", "private": True, "dependencies": {}}

    def dependencies(self, manifest: dict[str, object]) -> dict[str, str]:
        dependencies = manifest.get("dependencies", {})
        if not isinstance(dependencies, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in dependencies.items()
        ):
            raise PackageManagerError("npm manifest dependencies must be a string-to-string object.")
        return dict(dependencies)

    def validate_manifest(self, manifest: object) -> dict[str, object]:
        if not isinstance(manifest, dict):
            raise PackageManagerError("npm manifest must be a JSON object.")
        if manifest.get("private") is not True:
            raise PackageManagerError("Managed npm manifest must remain private.")
        dependencies = self.dependencies(manifest)
        for name, version in dependencies.items():
            parsed_name, parsed_version = self.validate_spec(f"{name}@{version}")
            if parsed_name != name or parsed_version != version:
                raise PackageManagerError("npm manifest contains an invalid package specification.")
        return dict(manifest)

    def lock_status(self, sandbox: str, manifest_path: Path, lock_path: Path) -> str:
        if manifest_path.is_symlink() or lock_path.is_symlink():
            return "INVALID"
        if not manifest_path.exists():
            return "NONE"
        if not lock_path.exists():
            return "OUT OF DATE"
        try:
            manifest = self.validate_manifest(_read_json(manifest_path))
            lock = _read_json(lock_path)
            if not isinstance(lock, dict) or not isinstance(lock.get("packages"), dict):
                return "INVALID"
            root_package = lock["packages"].get("")
            if not isinstance(root_package, dict):
                return "INVALID"
            locked_dependencies = root_package.get("dependencies", {})
            return "UP TO DATE" if locked_dependencies == self.dependencies(manifest) else "OUT OF DATE"
        except (PackageManagerError, ValueError):
            return "INVALID"

    def resolved_versions(self, sandbox: str, dependencies: dict[str, str]) -> dict[str, str]:
        lock_path = _lock_path(sandbox, self.ecosystem_id)
        if self.lock_status(sandbox, _manifest_path(sandbox, self.ecosystem_id), lock_path) != "UP TO DATE":
            return {}
        try:
            lock_data = _read_json(lock_path)
            packages = lock_data.get("packages", {}) if isinstance(lock_data, dict) else {}
            if not isinstance(packages, dict):
                return {}
            return {
                name: item["version"]
                for name in dependencies
                if isinstance((item := packages.get(f"node_modules/{name}")), dict)
                and isinstance(item.get("version"), str)
            }
        except PackageManagerError:
            return {}

    def lock(self, sandbox: str) -> PackageResult:
        validate_name(sandbox)
        manifest_path = _manifest_path(sandbox, self.ecosystem_id)
        if not manifest_path.exists():
            raise PackageManagerError(f"Package configuration was not found: {manifest_path}", exit_code=3)
        manifest = self.validate_manifest(_read_json(manifest_path))
        from ..infrastructure.openshell.sandbox import execute_sandbox_argv, sandbox_status
        from ..infrastructure.openshell.sandbox_files import (
            create_sandbox_workspace_directory,
            read_sandbox_workspace_text_file,
            delete_sandbox_workspace_directory,
            write_sandbox_file,
        )
        metadata = json.loads(sandbox_status(sandbox))
        if not isinstance(metadata, dict) or metadata.get("profile", "default") != self.network_profile:
            raise PackageManagerError("npm lock requires a default-profile sandbox with the npm registry network policy.", exit_code=4)
        stage = f".mcp-package-lock-{sandbox}"
        _sandbox_path_preflight(sandbox, stage, allow_existing=False)
        create_sandbox_workspace_directory(sandbox, stage)
        cleanup_error: Exception | None = None
        try:
            write_sandbox_file(
                sandbox,
                f"{stage}/package.json",
                json.dumps(manifest, indent=2) + "\n",
                overwrite=False,
            )
            result = execute_sandbox_argv(sandbox, ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund", "--prefix", f"/workspace/project/{stage}"], timeout_seconds=120)
            if int(result.get("return_code", 1)) != 0:
                detail = str(result.get("stderr") or result.get("stdout") or "npm resolution failed").strip()
                raise PackageManagerError(f"npm dependency resolution failed; existing lockfile preserved. Reason: {detail}")
            lock_text = read_sandbox_workspace_text_file(sandbox, f"{stage}/package-lock.json")
            try:
                lock_data = json.loads(lock_text)
            except json.JSONDecodeError as exc:
                raise PackageManagerError("npm produced an invalid package-lock.json; existing lockfile preserved.") from exc
            if not isinstance(lock_data, dict) or not isinstance(lock_data.get("packages"), dict):
                raise PackageManagerError("npm produced an unsupported lockfile; existing lockfile preserved.")
            lock_path = _lock_path(sandbox, self.ecosystem_id)
            _atomic_json(lock_path, lock_data)
            return PackageResult("lock", sandbox, self.ecosystem_id, "Dependency resolution completed; lockfile is UP TO DATE.", manifest_path, lock_path, "locked")
        finally:
            try:
                delete_sandbox_workspace_directory(sandbox, stage)
            except Exception as exc:
                cleanup_error = exc
            if cleanup_error is not None:
                raise PackageManagerError(
                    f"Package lock operation left temporary staging state at {stage}; cleanup failed: {type(cleanup_error).__name__}. Inspect the sandbox before retrying."
                ) from cleanup_error

    def install(self, sandbox: str, *, confirmed: bool, no_input: bool) -> PackageResult:
        validate_name(sandbox)
        manifest_path = _manifest_path(sandbox, self.ecosystem_id)
        lock_path = _lock_path(sandbox, self.ecosystem_id)
        if not manifest_path.exists():
            raise PackageManagerError(f"Package configuration was not found: {manifest_path}", exit_code=3)
        if not lock_path.exists():
            raise PackageManagerError(f"Required lockfile is missing: {lock_path}. Run mcpctl sandbox packages lock {sandbox} --ecosystem {self.ecosystem_id}.", exit_code=3)
        if self.lock_status(sandbox, manifest_path, lock_path) != "UP TO DATE":
            raise PackageManagerError(f"Lockfile is not current: {lock_path}. Run the lock command before installing.")
        _confirm("package installation", sandbox, self.ecosystem_id, confirmed=confirmed, no_input=no_input)
        manifest = self.validate_manifest(_read_json(manifest_path))
        lock_data = _read_json(lock_path)
        from ..infrastructure.openshell.sandbox import execute_sandbox_argv, sandbox_status
        from ..infrastructure.openshell.sandbox_files import (
            create_sandbox_workspace_directory,
        )
        metadata = json.loads(sandbox_status(sandbox))
        if not isinstance(metadata, dict) or metadata.get("profile", "default") != self.network_profile:
            raise PackageManagerError("npm install requires a default-profile sandbox with the npm registry network policy.", exit_code=4)
        install_root = self.install_relative_path
        marker_path = f"{install_root}/.mcp-managed.json"
        manifest_relative = f"{install_root}/package.json"
        lock_relative = f"{install_root}/package-lock.json"
        _sandbox_path_preflight(sandbox, install_root, allow_existing=True)
        for managed_file in (marker_path, manifest_relative, lock_relative):
            _sandbox_path_preflight(sandbox, managed_file, allow_existing=True, directory=False)
        _sandbox_path_preflight(sandbox, f"{install_root}/node_modules", allow_existing=True)
        created_install_root = False
        try:
            create_sandbox_workspace_directory(sandbox, install_root)
            created_install_root = True
        except Exception as exc:
            from ..infrastructure.openshell.sandbox_files import read_sandbox_workspace_text_file
            try:
                marker = json.loads(read_sandbox_workspace_text_file(sandbox, marker_path))
            except Exception:
                raise PackageManagerError(f"Install path already exists and is not verified as managed: {install_root}") from exc
            if marker != {"schema_version": 1, "managed_by": "mcpctl", "ecosystem": self.ecosystem_id}:
                raise PackageManagerError(f"Install path marker is invalid; refusing to modify {install_root}.")
        try:
            from ..infrastructure.openshell.sandbox_files import write_sandbox_file
            if created_install_root:
                write_sandbox_file(
                    sandbox,
                    marker_path,
                    json.dumps({"schema_version": 1, "managed_by": "mcpctl", "ecosystem": self.ecosystem_id}) + "\n",
                    overwrite=False,
                )
            for rel, payload in (
                (manifest_relative, json.dumps(manifest, indent=2) + "\n"),
                (lock_relative, json.dumps(lock_data, indent=2) + "\n"),
            ):
                write_sandbox_file(sandbox, rel, payload, overwrite=True)
            result = execute_sandbox_argv(sandbox, ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--prefix", f"/workspace/project/{install_root}"], timeout_seconds=300)
            if int(result.get("return_code", 1)) != 0:
                detail = _sanitize_diagnostic(str(result.get("stderr") or result.get("stdout") or "npm install failed").strip())
                verified = self.verify_installation(sandbox)
                raise PackageManagerError(f"npm installation failed. Environment status: {verified}. Reason: {detail}")
            verified = self.verify_installation(sandbox)
            if verified != "INSTALLED":
                raise PackageManagerError(f"npm exited successfully but installation verification returned {verified}.")
            return PackageResult("install", sandbox, self.ecosystem_id, "Locked dependencies installed and verified.", manifest_path, lock_path, "installed")
        except PackageManagerError:
            raise
        except Exception as exc:
            raise PackageManagerError(f"Package installation failed; inspect sandbox state. Reason: {type(exc).__name__}: {exc}") from exc

    def verify_installation(self, sandbox: str) -> str:
        from ..infrastructure.openshell.sandbox import execute_sandbox_argv, sandbox_status
        metadata = json.loads(sandbox_status(sandbox))
        profile = metadata.get("profile", "default") if isinstance(metadata, dict) else "default"
        if profile != self.network_profile:
            return "UNAVAILABLE"
        if _lock_status(sandbox, self.ecosystem_id) != "UP TO DATE":
            return "REQUIRES VERIFICATION"
        result = execute_sandbox_argv(sandbox, ["npm", "ls", "--json", "--depth=0", "--prefix", f"/workspace/project/{self.install_relative_path}"], timeout_seconds=20)
        if int(result.get("return_code", 1)) == 0:
            return "INSTALLED"
        output = result.get("stdout")
        try:
            listing = json.loads(output) if isinstance(output, str) else {}
        except json.JSONDecodeError:
            listing = {}
        actual = listing.get("dependencies", {}) if isinstance(listing, dict) else {}
        if not isinstance(actual, dict):
            actual = {}
        installed_direct = [
            name for name, item in actual.items()
            if isinstance(item, dict) and isinstance(item.get("version"), str)
        ]
        return "PARTIAL" if installed_direct else "NOT INSTALLED"


# Registry is the single source of truth for available ecosystems. New adapters
# register here; core CLI logic remains ecosystem-agnostic.
_ADAPTERS: dict[str, EcosystemAdapter] = {"npm": NpmAdapter()}


def _ensure_python_adapter() -> None:
    """Load optional built-in adapters only after this module is initialized."""
    if "python" not in _ADAPTERS:
        from .adapters.python_uv import PythonUvAdapter

        _ADAPTERS["python"] = PythonUvAdapter()


def registered_ecosystems() -> tuple[str, ...]:
    _ensure_python_adapter()
    return tuple(sorted(_ADAPTERS))


def get_adapter(ecosystem: str) -> EcosystemAdapter:
    _ensure_python_adapter()
    adapter = _ADAPTERS.get(ecosystem)
    if adapter is None:
        raise PackageManagerError(
            f"Ecosystem {ecosystem!r} is not registered. Registered ecosystems: "
            + (", ".join(registered_ecosystems()) or "none")
            + ".",
            exit_code=2,
        )
    return adapter


def _state_root() -> Path:
    configured = os.environ.get("MCP_STATE_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise PackageManagerError("MCP_STATE_DIR must be an absolute path.")
        return path
    return app_state_root() / "mcp"


def package_root(sandbox: str, ecosystem: str) -> Path:
    validate_name(sandbox)
    get_adapter(ecosystem)
    root = _state_root() / "sandboxes" / sandbox / "packages" / ecosystem
    resolved_root = root.resolve()
    state_root = _state_root().resolve()
    if not resolved_root.is_relative_to(state_root):
        raise PackageManagerError("Package state path escapes MCP_STATE_DIR.")
    return root


def _safe_managed_dir(path: Path, *, create: bool = False) -> Path:
    root = _state_root()
    if root.is_symlink():
        raise PackageManagerError("MCP_STATE_DIR must not be a symbolic link.")
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise PackageManagerError("Managed package path is outside MCP_STATE_DIR.")
    except OSError as exc:
        raise PackageManagerError("Managed package path could not be resolved safely.") from exc

    current = path
    while current != root and current != current.parent:
        if current.is_symlink():
            raise PackageManagerError(f"Managed package path must not contain symlinks: {current}")
        current = current.parent
    if current != root:
        raise PackageManagerError("Managed package path is outside MCP_STATE_DIR.")

    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink():
            raise PackageManagerError("MCP_STATE_DIR must not be a symbolic link.")
        relative_parts = path.relative_to(root).parts
        current = root
        for part in relative_parts:
            current = current / part
            if current.is_symlink():
                raise PackageManagerError(f"Managed package path must not contain symlinks: {current}")
            current.mkdir(exist_ok=True, mode=0o700)
    return path


def _manifest_path(sandbox: str, ecosystem: str) -> Path:
    return package_root(sandbox, ecosystem) / get_adapter(ecosystem).manifest_name


def _lock_path(sandbox: str, ecosystem: str) -> Path:
    return package_root(sandbox, ecosystem) / get_adapter(ecosystem).lock_name


def _read_json(path: Path) -> object:
    if path.is_symlink():
        raise PackageManagerError(f"Managed package file must not be a symlink: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PackageManagerError(f"Required package file was not found: {path}", exit_code=3) from None
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageManagerError(f"Could not read valid JSON from {path}: {type(exc).__name__}") from exc


def _sanitize_diagnostic(value: str) -> str:
    value = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1[REDACTED]@", value)
    value = re.sub(
        r"(?i)(authorization|token|password|_authToken)(\s*[:=]\s*)[^\s,]+",
        r"\1\2[REDACTED]",
        value,
    )
    return value[:2000]


def _atomic_json(path: Path, value: object) -> None:
    _safe_managed_dir(path.parent, create=True)
    if path.is_symlink():
        raise PackageManagerError(f"Refusing to replace symlink: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=".package.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise PackageManagerError(f"Could not atomically write {path}: {type(exc).__name__}") from exc
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _lock_status(sandbox: str, ecosystem: str) -> str:
    adapter = get_adapter(ecosystem)
    return adapter.lock_status(
        sandbox, _manifest_path(sandbox, ecosystem), _lock_path(sandbox, ecosystem)
    )


def validate_sandbox_capabilities(sandbox: str, ecosystem: str, profile: str) -> None:
    adapter = get_adapter(ecosystem)
    if profile != adapter.network_profile:
        raise PackageManagerError(
            f"Ecosystem {ecosystem!r} requires sandbox profile {adapter.network_profile!r}; "
            f"selected profile is {profile!r}.",
            exit_code=4,
        )
    from ..infrastructure.openshell.sandbox import execute_sandbox_argv
    result = execute_sandbox_argv(sandbox, list(adapter.runtime_argv), timeout_seconds=15)
    if int(result.get("return_code", 1)) != 0:
        detail = str(result.get("stderr") or result.get("stdout") or "runtime probe failed").strip()
        raise PackageManagerError(
            f"Runtime prerequisites for ecosystem {ecosystem!r} are not met: {detail}",
            exit_code=4,
        )


def initialize_sandbox_packages(sandbox: str, ecosystem: str) -> PackageResult:
    adapter = get_adapter(ecosystem)
    root = package_root(sandbox, ecosystem)
    manifest = _manifest_path(sandbox, ecosystem)
    root_was_present = root.exists()
    try:
        _safe_managed_dir(root, create=True)
        if manifest.is_symlink():
            raise PackageManagerError(f"Managed package manifest must not be a symlink: {manifest}")
        if manifest.exists():
            adapter.validate_manifest(_read_json(manifest))
            return PackageResult(
                "initialize", sandbox, ecosystem,
                "Existing package configuration preserved; no packages installed.",
                manifest, _lock_path(sandbox, ecosystem), "configured",
            )
        if _lock_path(sandbox, ecosystem).exists() or _lock_path(sandbox, ecosystem).is_symlink():
            raise PackageManagerError(f"Orphaned lockfile exists without a manifest: {_lock_path(sandbox, ecosystem)}")
        _atomic_json(manifest, adapter.base_manifest(sandbox))
    except Exception as exc:
        if not root_was_present and root.exists() and not root.is_symlink():
            try:
                shutil.rmtree(root)
            except OSError as cleanup_error:
                raise PackageManagerError(
                    f"Package initialization failed and its newly created state directory "
                    f"could not be cleaned up: {root} ({type(cleanup_error).__name__})."
                ) from exc
        raise
    return PackageResult("initialize", sandbox, ecosystem, "Package configuration initialized; no packages installed.", manifest, _lock_path(sandbox, ecosystem), "configured")


def list_packages(sandbox: str, ecosystem: str | None = None) -> dict[str, object]:
    validate_name(sandbox)
    ecosystems = (ecosystem,) if ecosystem else registered_ecosystems()
    result: dict[str, object] = {"sandbox": sandbox, "ecosystems": []}
    records: list[dict[str, object]] = []
    for ecosystem_id in ecosystems:
        adapter = get_adapter(ecosystem_id)
        manifest_path = _manifest_path(sandbox, ecosystem_id)
        lock_path = _lock_path(sandbox, ecosystem_id)
        if manifest_path.is_symlink():
            raise PackageManagerError(f"Managed package manifest must not be a symlink: {manifest_path}")
        if not manifest_path.exists():
            continue
        manifest = adapter.validate_manifest(_read_json(manifest_path))
        dependencies = adapter.dependencies(manifest)
        resolved_versions = adapter.resolved_versions(sandbox, dependencies)
        for name, requested in sorted(dependencies.items()):
            records.append({
                "ecosystem": ecosystem_id,
                "package": name,
                "requested": requested,
                "resolved": resolved_versions.get(name, "-"),
                "status": "configured",
            })
        result["ecosystems"].append({
            "id": ecosystem_id,
            "manifest": str(manifest_path.resolve()),
            "lockfile": str(lock_path.resolve()) if lock_path.exists() else str(lock_path),
            "lock_status": _lock_status(sandbox, ecosystem_id),
            "installation_status": "UNKNOWN",
            "package_count": len(dependencies),
        })
    result["packages"] = records
    return result


def add_package(sandbox: str, ecosystem: str, package_spec: str) -> PackageResult:
    validate_name(sandbox)
    adapter = get_adapter(ecosystem)
    name, version = adapter.validate_spec(package_spec)

    manifest_path = _manifest_path(sandbox, ecosystem)
    initialized = False
    if not manifest_path.exists():
        # Reuse the same safe, idempotent initializer used by sandbox creation.
        # This makes first-time package addition work for existing sandboxes
        # without duplicating manifest creation or bypassing path validation.
        initialize_sandbox_packages(sandbox, ecosystem)
        manifest_path = _manifest_path(sandbox, ecosystem)
        initialized = True

    manifest = adapter.validate_manifest(_read_json(manifest_path))
    dependencies = adapter.dependencies(manifest)
    if name in dependencies:
        raise PackageManagerError(
            f"Package {name!r} is already configured for ecosystem {ecosystem!r}."
        )
    dependencies[name] = version
    manifest["dependencies"] = dict(sorted(dependencies.items()))
    _atomic_json(manifest_path, manifest)

    if initialized:
        message = (
            f"Initialized package configuration and added {name}. "
            "Lock is OUT OF DATE; installation is NOT VERIFIED."
        )
    else:
        message = (
            f"Added {name} to package configuration. "
            "Lock is OUT OF DATE; installation is NOT VERIFIED."
        )
    return PackageResult(
        "add",
        sandbox,
        ecosystem,
        message,
        manifest_path,
        _lock_path(sandbox, ecosystem),
        "configured",
    )


def remove_package(sandbox: str, ecosystem: str, package_name: str) -> PackageResult:
    validate_name(sandbox)
    adapter = get_adapter(ecosystem)
    name, version = adapter.validate_spec(package_name)
    if version != "*":
        raise ValueError("Remove expects a package name without a version.")
    manifest_path = _manifest_path(sandbox, ecosystem)
    if not manifest_path.exists():
        raise PackageManagerError(f"Package configuration was not found: {manifest_path}", exit_code=3)
    manifest = adapter.validate_manifest(_read_json(manifest_path))
    dependencies = adapter.dependencies(manifest)
    if name not in dependencies:
        raise PackageManagerError(f"Package {name!r} is not configured for ecosystem {ecosystem!r}.")
    del dependencies[name]
    manifest["dependencies"] = dict(sorted(dependencies.items()))
    _atomic_json(manifest_path, manifest)
    return PackageResult("remove", sandbox, ecosystem, f"Removed {name} from configuration. Lock is OUT OF DATE; installed environment is UNCHANGED.", manifest_path, _lock_path(sandbox, ecosystem), "configured")


def show_packages(sandbox: str, ecosystem: str | None = None) -> dict[str, object]:
    validate_name(sandbox)
    ecosystems = (ecosystem,) if ecosystem else registered_ecosystems()
    records: list[dict[str, object]] = []
    for ecosystem_id in ecosystems:
        adapter = get_adapter(ecosystem_id)
        root = package_root(sandbox, ecosystem_id)
        manifest = _manifest_path(sandbox, ecosystem_id)
        lock = _lock_path(sandbox, ecosystem_id)
        records.append({
            "ecosystem": ecosystem_id,
            "adapter_status": "AVAILABLE",
            "package_manager": adapter.package_manager,
            "manifest": str(manifest.resolve()) if manifest.exists() else str(manifest),
            "manifest_status": "INVALID (SYMLINK)" if manifest.is_symlink() else ("PRESENT" if manifest.exists() else "NONE"),
            "lockfile": str(lock.resolve()) if lock.exists() else str(lock),
            "lock_status": _lock_status(sandbox, ecosystem_id),
            "installation_status": _verified_installation_or_unknown(sandbox, ecosystem_id) if manifest.exists() else "NONE",
            "package_state_root": str(root.resolve()) if root.exists() else str(root),
        })
    return {"sandbox": sandbox, "package_state_root": str(_state_root().resolve()), "ecosystems": records}


def reset_packages(sandbox: str, ecosystem: str, *, confirmed: bool) -> PackageResult:
    validate_name(sandbox)
    adapter = get_adapter(ecosystem)
    if not confirmed:
        raise PackageManagerError("packages reset requires explicit confirmation; use --yes.")
    manifest = _manifest_path(sandbox, ecosystem)
    lock = _lock_path(sandbox, ecosystem)
    if manifest.is_symlink():
        raise PackageManagerError(f"Managed package manifest must not be a symlink: {manifest}")
    if not manifest.exists():
        raise PackageManagerError(f"Package configuration was not found: {manifest}", exit_code=3)
    if lock.is_symlink() or (lock.exists() and not lock.is_file()):
        raise PackageManagerError(f"Refusing to reset with an unsafe lockfile target: {lock}")
    base = adapter.base_manifest(sandbox)
    _atomic_json(manifest, base)
    if lock.exists():
        try:
            lock.unlink()
        except OSError as exc:
            raise PackageManagerError(
                f"Base manifest was reset, but the old lockfile could not be removed: {lock}. "
                "Package state requires inspection; installation is not verified."
            ) from exc
    return PackageResult("reset", sandbox, ecosystem, "Additional package configuration reset to base; lock is OUT OF DATE; installation REQUIRES VERIFICATION.", manifest, lock, "configured")


def verify_installation(sandbox: str, ecosystem: str) -> str:
    return get_adapter(ecosystem).verify_installation(sandbox)


def _confirm(operation: str, sandbox: str, ecosystem: str, *, confirmed: bool, no_input: bool) -> None:
    if confirmed:
        return
    import sys
    if no_input or not sys.stdin.isatty():
        raise PackageManagerError(f"{operation} requires confirmation; rerun with --yes in an authorized environment.", exit_code=2)
    answer = input(f"Confirm {operation} for sandbox {sandbox!r}, ecosystem {ecosystem!r}? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise PackageManagerError("Cancelled. No package operation was started.")


def _sandbox_path_preflight(
    sandbox: str, relative_path: str, *, allow_existing: bool, directory: bool = True
) -> None:
    from ..infrastructure.openshell.sandbox import execute_sandbox_argv

    script = (
        "import os,sys; root=os.path.realpath('/workspace/project'); "
        "rel=sys.argv[1]; target=os.path.join(root,rel); "
        "parts=rel.split('/'); cur=root; "
        "[(None if not os.path.islink(cur:=os.path.join(cur,p)) else "
        "(_ for _ in ()).throw(SystemExit('managed path contains a symlink'))) for p in parts]; "
        "resolved=os.path.realpath(target); "
        "(_ for _ in ()).throw(SystemExit('managed path escapes workspace')) "
        "if os.path.commonpath([root,resolved])!=root else None; "
        "(_ for _ in ()).throw(SystemExit('managed path already exists')) "
        "if (not " + ("True" if allow_existing else "False") + ") and os.path.lexists(target) else None; "
        "(_ for _ in ()).throw(SystemExit('managed path has the wrong file type')) "
        "if os.path.lexists(target) and not os.path." + ("isdir" if directory else "isfile") + "(target) else None"
    )
    result = execute_sandbox_argv(
        sandbox, ["python", "-c", script, relative_path], timeout_seconds=15
    )
    if int(result.get("return_code", 1)) != 0:
        detail = _sanitize_diagnostic(str(result.get("stderr") or result.get("stdout") or "path preflight failed").strip())
        raise PackageManagerError(f"Unsafe sandbox package path {relative_path!r}: {detail}")


def lock_packages(sandbox: str, ecosystem: str) -> PackageResult:
    validate_name(sandbox)
    return get_adapter(ecosystem).lock(sandbox)


def install_packages(
    sandbox: str, ecosystem: str, *, confirmed: bool = False, no_input: bool = False
) -> PackageResult:
    validate_name(sandbox)
    return get_adapter(ecosystem).install(
        sandbox, confirmed=confirmed, no_input=no_input
    )


def _verified_installation_or_unknown(sandbox: str, ecosystem: str) -> str:
    try:
        return verify_installation(sandbox, ecosystem)
    except Exception:
        return "UNKNOWN"


def sandbox_package_summary(sandbox: str) -> dict[str, object]:
    return show_packages(sandbox)


def delete_package_state(sandbox: str, *, purge: bool = False) -> dict[str, object]:
    validate_name(sandbox)
    root = _state_root() / "sandboxes" / sandbox / "packages"
    _safe_managed_dir(root, create=False)
    if root.is_symlink():
        raise PackageManagerError(f"Refusing to follow symlinked package state: {root}")
    if not root.exists():
        return {"sandbox": sandbox, "package_state": "NONE", "removed": False}
    if not purge:
        return {"sandbox": sandbox, "package_state": "PRESERVED", "removed": False, "path": str(root.resolve())}
    if not root.is_dir():
        raise PackageManagerError(f"Refusing to purge unsafe package state path: {root}")

    targets: list[tuple[str, Path]] = []
    for ecosystem in registered_ecosystems():
        target = root / ecosystem
        _safe_managed_dir(target, create=False)
        if target.is_symlink():
            raise PackageManagerError(f"Refusing to purge symlinked ecosystem state: {target}")
        if not target.exists():
            continue
        if not target.is_dir():
            raise PackageManagerError(f"Refusing to purge non-directory ecosystem state: {target}")
        targets.append((ecosystem, target))

    removed: list[str] = []
    preserved: list[str] = []
    for ecosystem, target in targets:
        try:
            shutil.rmtree(target)
            if target.exists() or target.is_symlink():
                raise OSError("target still exists after recursive removal")
            removed.append(ecosystem)
        except OSError as exc:
            raise PackageManagerError(
                f"Package purge partially failed; removed ecosystems: {', '.join(removed) or 'none'}; "
                f"failed target: {target}; reason: {type(exc).__name__}. Inspect package state before retrying."
            ) from exc

    for child in root.iterdir():
        preserved.append(child.name)
    if not preserved:
        root.rmdir()
    return {
        "sandbox": sandbox,
        "package_state": "REMOVED" if not preserved else "PARTIALLY REMOVED",
        "removed": not preserved,
        "removed_ecosystems": removed,
        "preserved_entries": preserved,
        "path": str(root),
    }
