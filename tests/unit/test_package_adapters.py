from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from local_mcp_server.packages import manager
from local_mcp_server.packages.adapters.python_uv import (
    PythonUvAdapter,
    _LOCK_BODY_HEADER,
    _LOCK_HEADER,
    _manifest_digest,
)


@pytest.fixture
def python_adapter() -> PythonUvAdapter:
    return manager.get_adapter("python")  # type: ignore[return-value]


def _lock_content(manifest: dict[str, object], body: str) -> str:
    if body and not body.endswith("\n"):
        body += "\n"
    return (
        _LOCK_HEADER
        + _manifest_digest(manifest)
        + "\n"
        + _LOCK_BODY_HEADER
        + hashlib.sha256(body.encode("utf-8")).hexdigest()
        + "\n"
        + body
    )


def test_python_adapter_accepts_pep_508_style_version_specifiers(
    python_adapter: PythonUvAdapter,
) -> None:
    assert python_adapter.validate_spec("requests") == ("requests", "*")
    assert python_adapter.validate_spec("Requests>=2.31,<3") == (
        "requests",
        ">=2.31,<3",
    )
    assert python_adapter.validate_spec("my_package~=1.4") == (
        "my-package",
        "~=1.4",
    )
    assert python_adapter.validate_spec("urllib3!=2.0.0") == (
        "urllib3",
        "!=2.0.0",
    )


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "../escape",
        "requests @ https://example.invalid/requests.whl",
        "git+https://example.invalid/repo.git",
        "file:../local",
        "requests[security]",
        "requests===",
        "requests>=2; python_version>='3.12'",
        "requests\nother",
        "requests==1.0\\n--index-url=https://evil.invalid",
    ],
)
def test_python_adapter_rejects_unsafe_or_unsupported_specs(
    python_adapter: PythonUvAdapter, spec: str
) -> None:
    with pytest.raises(ValueError):
        python_adapter.validate_spec(spec)


def test_python_manifest_rejects_invalid_dependency_specs(
    python_adapter: PythonUvAdapter,
) -> None:
    manifest = python_adapter.base_manifest("sandbox-one")
    manifest["dependencies"] = {"requests": "=== "}
    with pytest.raises(manager.PackageManagerError, match="invalid package specification"):
        python_adapter.validate_manifest(manifest)


def test_python_configuration_and_lock_state_are_separate_from_npm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("MCP_STATE_DIR", str(state))

    npm = manager.initialize_sandbox_packages("sandbox-one", "npm")
    python = manager.initialize_sandbox_packages("sandbox-one", "python")
    manager.add_package("sandbox-one", "npm", "express@^5")
    manager.add_package("sandbox-one", "python", "requests>=2.31,<3")

    npm_manifest = json.loads(npm.manifest.read_text(encoding="utf-8"))
    python_manifest = json.loads(python.manifest.read_text(encoding="utf-8"))
    assert npm_manifest["dependencies"] == {"express": "^5"}
    assert python_manifest["dependencies"] == {"requests": ">=2.31,<3"}
    assert npm.manifest != python.manifest
    assert npm.manifest.parent != python.manifest.parent
    assert manager.registered_ecosystems() == ("npm", "python")


def test_empty_python_manifest_locks_without_package_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import local_mcp_server.infrastructure.openshell.sandbox as sandbox_api
    import local_mcp_server.packages.adapters.python_uv as python_uv_module

    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    manager.initialize_sandbox_packages("sandbox-one", "python")
    monkeypatch.setattr(
        sandbox_api, "sandbox_status", lambda _name: '{"profile":"default"}'
    )
    monkeypatch.setattr(
        python_uv_module,
        "_sandbox_path_preflight",
        lambda *_args, **_kwargs: pytest.fail("empty lock must not stage a resolver"),
    )
    result = manager.lock_packages("sandbox-one", "python")
    assert result.status == "locked"
    assert result.lockfile is not None
    assert manager._lock_status("sandbox-one", "python") == "UP TO DATE"
    assert len(result.lockfile.read_text(encoding="utf-8").splitlines()) == 2


def test_python_lock_status_tracks_manifest_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    result = manager.initialize_sandbox_packages("sandbox-one", "python")
    manifest = manager._read_json(result.manifest)
    assert isinstance(manifest, dict)
    lock = manager._lock_path("sandbox-one", "python")
    lock.write_text(
        _lock_content(
            manifest,
            "requests==2.32.0 --hash=sha256:" + ("a" * 64) + "\n",
        ),
        encoding="utf-8",
    )
    assert manager._lock_status("sandbox-one", "python") == "UP TO DATE"

    manager.add_package("sandbox-one", "python", "urllib3>=2")
    assert manager._lock_status("sandbox-one", "python") == "OUT OF DATE"


def test_python_lock_status_rejects_tampered_lock_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    result = manager.initialize_sandbox_packages("sandbox-one", "python")
    manifest = manager._read_json(result.manifest)
    assert isinstance(manifest, dict)
    lock = manager._lock_path("sandbox-one", "python")
    lock.write_text(
        _lock_content(
            manifest,
            "requests==2.32.0 --hash=sha256:" + ("a" * 64) + "\n",
        ),
        encoding="utf-8",
    )
    assert manager._lock_status("sandbox-one", "python") == "UP TO DATE"
    lock.write_text(lock.read_text(encoding="utf-8").replace("2.32.0", "2.32.1"), encoding="utf-8")
    assert manager._lock_status("sandbox-one", "python") == "INVALID"


def test_python_lockfile_symlink_is_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    manager.initialize_sandbox_packages("sandbox-one", "python")
    outside = tmp_path / "outside.lock"
    outside.write_text("do not follow", encoding="utf-8")
    lock = manager._lock_path("sandbox-one", "python")
    lock.symlink_to(outside)
    assert manager._lock_status("sandbox-one", "python") == "INVALID"
    assert outside.read_text(encoding="utf-8") == "do not follow"


def test_python_capability_validation_rejects_browser_profile() -> None:
    with pytest.raises(manager.PackageManagerError, match="requires sandbox profile") as exc:
        manager.validate_sandbox_capabilities("sandbox-one", "python", "browser")
    assert exc.value.exit_code == 4


def test_python_install_uses_hashed_lock_and_managed_venv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import local_mcp_server.infrastructure.openshell.sandbox as sandbox_api
    import local_mcp_server.infrastructure.openshell.sandbox_files as sandbox_files
    import local_mcp_server.packages.adapters.python_uv as python_uv_module

    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))
    initialized = manager.initialize_sandbox_packages("sandbox-one", "python")
    manager.add_package("sandbox-one", "python", "requests>=2.31")
    manifest = manager._read_json(initialized.manifest)
    assert isinstance(manifest, dict)
    lock = manager._lock_path("sandbox-one", "python")
    lock.write_text(
        _lock_content(
            manifest,
            "requests==2.32.0 --hash=sha256:" + ("a" * 64) + "\n",
        ),
        encoding="utf-8",
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        sandbox_api, "sandbox_status", lambda _name: '{"profile":"default"}'
    )

    def fake_execute(
        _sandbox: str, argv: list[str], *, timeout_seconds: int
    ) -> dict[str, object]:
        calls.append(list(argv))
        if argv[:3] == ["uv", "pip", "freeze"]:
            return {
                "stdout": "requests==2.32.0\n",
                "stderr": "",
                "return_code": 0,
            }
        return {"stdout": "", "stderr": "", "return_code": 0}

    monkeypatch.setattr(sandbox_api, "execute_sandbox_argv", fake_execute)
    monkeypatch.setattr(
        python_uv_module, "_sandbox_path_preflight", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        sandbox_files,
        "create_sandbox_workspace_directory",
        lambda *_args, **_kwargs: "created",
    )
    monkeypatch.setattr(
        sandbox_files, "write_sandbox_file", lambda *_args, **_kwargs: "written"
    )

    result = manager.install_packages(
        "sandbox-one", "python", confirmed=True, no_input=True
    )

    assert result.status == "installed"
    sync = next(call for call in calls if call[:3] == ["uv", "pip", "sync"])
    assert "--only-binary" in sync
    assert "--require-hashes" in sync
    assert "--python" in sync
    assert not any(call[:2] == ["sh", "-c"] for call in calls)
