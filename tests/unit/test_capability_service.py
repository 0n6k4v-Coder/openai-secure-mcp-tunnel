import pytest
from unittest.mock import patch

from local_mcp_server.capability.service import (
    CapabilityError,
    get_capability_stats,
    grant_capability,
    inspect_sandbox_capabilities,
    list_capabilities,
    revoke_capability,
)


@pytest.fixture
def temp_state_dir(tmp_path):
    with patch("local_mcp_server.capability.service._get_state_path", return_value=tmp_path / "capabilities.json"):
        yield tmp_path


def test_grant_and_list_capability(temp_state_dir):
    res = grant_capability("jupyter-dev", "docker", ttl_seconds=3600)
    assert res["capability"] == "docker"
    assert res["sandbox"] == "jupyter-dev"
    assert res["expires_at"] is not None

    grants = list_capabilities()
    assert "docker" in grants
    assert "jupyter-dev" in grants["docker"]

    single = list_capabilities("jupyter-dev")
    assert "docker" in single


def test_grant_invalid_capability(temp_state_dir):
    with pytest.raises(CapabilityError, match="Invalid capability"):
        grant_capability("jupyter-dev", "invalid-cap")


def test_revoke_capability(temp_state_dir):
    grant_capability("jupyter-dev", "openshell")
    assert revoke_capability("jupyter-dev", "openshell") is True
    assert revoke_capability("jupyter-dev", "openshell") is False

    single = list_capabilities("jupyter-dev")
    assert "openshell" not in single


def test_capability_stats_accounting(temp_state_dir):
    grant_capability("s1", "docker")
    grant_capability("s2", "docker")
    stats = get_capability_stats()
    assert stats["active_grants"]["docker"] == 2
    assert stats["peak_concurrent"]["docker"] == 2
    assert stats["lifetime_grants"]["docker"] == 2

    revoke_capability("s1", "docker")
    stats2 = get_capability_stats()
    assert stats2["active_grants"]["docker"] == 1
    assert stats2["peak_concurrent"]["docker"] == 2
    assert stats2["lifetime_grants"]["docker"] == 2


def test_inspect_sandbox_capabilities(temp_state_dir):
    grant_capability("jupyter-dev", "docker")
    inspected = inspect_sandbox_capabilities("jupyter-dev")
    assert inspected["sandbox"] == "jupyter-dev"
    assert inspected["capabilities"]["docker"]["granted"] is True
    assert inspected["capabilities"]["openshell"]["granted"] is False
