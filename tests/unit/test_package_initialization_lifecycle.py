from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_mcp_server.packages import manager


@pytest.mark.parametrize(
    ("ecosystem", "package_spec", "expected_dependencies"),
    [
        ("npm", "express@^5", {"express": "^5"}),
        ("python", "requests>=2.31,<3", {"requests": ">=2.31,<3"}),
    ],
)
def test_first_add_initializes_missing_manifest_without_installing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ecosystem: str,
    package_spec: str,
    expected_dependencies: dict[str, str],
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))

    manifest = manager._manifest_path("project-jupyter", ecosystem)
    lockfile = manager._lock_path("project-jupyter", ecosystem)
    assert not manifest.exists()
    assert not lockfile.exists()

    result = manager.add_package("project-jupyter", ecosystem, package_spec)

    assert result.status == "configured"
    assert result.manifest == manifest
    assert manifest.is_file()
    assert "Initialized package configuration and added" in result.message
    assert "NOT VERIFIED" in result.message
    assert not lockfile.exists()

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["dependencies"] == expected_dependencies
    assert manager._lock_status("project-jupyter", ecosystem) == "OUT OF DATE"


@pytest.mark.parametrize(
    ("ecosystem", "package_spec"),
    [
        ("npm", "express@^5"),
        ("python", "requests>=2.31,<3"),
    ],
)
def test_first_add_refuses_orphan_lockfile_without_overwriting_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ecosystem: str,
    package_spec: str,
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))

    root = manager.package_root("project-jupyter", ecosystem)
    root.mkdir(parents=True)
    lockfile = manager._lock_path("project-jupyter", ecosystem)
    lock_contents = '{"preserve": true}\n'
    lockfile.write_text(lock_contents, encoding="utf-8")

    manifest = manager._manifest_path("project-jupyter", ecosystem)
    with pytest.raises(manager.PackageManagerError, match="Orphaned lockfile"):
        manager.add_package("project-jupyter", ecosystem, package_spec)

    assert not manifest.exists()
    assert lockfile.read_text(encoding="utf-8") == lock_contents


def test_first_add_does_not_follow_a_symlinked_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path / "state"))

    root = manager.package_root("project-jupyter", "python")
    root.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside_contents = json.dumps(
        {
            "schema_version": 1,
            "name": "outside",
            "private": True,
            "dependencies": {},
        }
    )
    outside.write_text(outside_contents, encoding="utf-8")

    manifest = manager._manifest_path("project-jupyter", "python")
    manifest.symlink_to(outside)

    with pytest.raises(manager.PackageManagerError, match="symlink"):
        manager.add_package("project-jupyter", "python", "requests>=2.31,<3")

    assert outside.read_text(encoding="utf-8") == outside_contents
