from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = (
    REPOSITORY_ROOT
    / "deploy"
    / "docker"
    / "workspace-acl-helper"
    / "entrypoint.sh"
)


def _helper_source() -> str:
    return HELPER_PATH.read_text(encoding="utf-8")


def _git_acl_section(source: str) -> str:
    marker = "    # Git metadata is handled separately from ordinary workspace files."
    assert marker in source
    section = source.split(marker, maxsplit=1)[1]
    return section.split("    exit 0\nfi", maxsplit=1)[0]


def test_host_and_sandbox_uids_must_differ() -> None:
    source = _helper_source()
    assert 'if [ "$host_uid" = "$sandbox_uid" ]; then' in source
    assert "host UID and sandbox UID must differ" in source


def test_git_metadata_has_a_dedicated_acl_policy() -> None:
    section = _git_acl_section(_helper_source())
    assert 'if [ -L "$root/.git" ]; then' in section
    assert 'find -P "$root/.git" -xdev -type d' in section
    assert 'find -P "$root/.git" -xdev -type f' in section


def test_git_metadata_grants_host_access_and_denies_sandbox_access() -> None:
    section = _git_acl_section(_helper_source())
    assert 'u::---,u:$host_uid:rwx' in section
    assert 'u:$sandbox_uid:---,u:$host_uid:rwx' in section
    assert 'u::---,u:$host_uid:rwX' in section
    assert 'u:$sandbox_uid:---,u:$host_uid:rwX' in section
    assert 'd:u:$sandbox_uid:---,d:u:$host_uid:rwx' in section


def test_git_metadata_remains_excluded_from_general_acl_walks() -> None:
    source = _helper_source()
    assert '-o -path "$root/.git"' in source
    assert """-o -path "$root/.git/"'*'""" in source


def test_git_symlink_is_rejected() -> None:
    section = _git_acl_section(_helper_source())
    assert 'if [ -L "$root/.git" ]; then' in section
    assert "workspace .git must not be a symbolic link" in section
