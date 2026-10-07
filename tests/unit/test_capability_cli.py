import pytest
from unittest.mock import patch

from local_mcp_server.cli.mcpctl import main


@pytest.fixture
def temp_state_dir(tmp_path):
    with patch("local_mcp_server.capability.service._get_state_path", return_value=tmp_path / "capabilities.json"):
        yield tmp_path


def test_cli_grant_and_list(temp_state_dir, capsys):
    ret = main(["capability", "grant", "box1", "docker", "--ttl", "1h"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "granted to sandbox 'box1'" in captured.out

    ret_list = main(["capability", "list"])
    assert ret_list == 0
    captured_list = capsys.readouterr()
    assert "box1" in captured_list.out


def test_cli_stats(temp_state_dir, capsys):
    main(["capability", "grant", "box1", "openshell"])
    capsys.readouterr()

    ret_stats = main(["capability", "stats"])
    assert ret_stats == 0
    captured = capsys.readouterr()
    assert "CAPABILITY" in captured.out
    assert "openshell" in captured.out


def test_cli_revoke(temp_state_dir, capsys):
    main(["capability", "grant", "box1", "docker"])
    capsys.readouterr()

    ret_rev = main(["capability", "revoke", "box1", "docker"])
    assert ret_rev == 0
    captured = capsys.readouterr()
    assert "revoked from sandbox 'box1'" in captured.out
