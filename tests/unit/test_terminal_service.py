from unittest.mock import MagicMock, patch

import pytest

from local_mcp_server.terminal.model import TerminalSessionStatus
from local_mcp_server.terminal.service import (
    TerminalError,
    close_terminal,
    get_terminal_state,
    list_terminals,
    open_terminal,
    resize_terminal,
    write_terminal,
)


@pytest.fixture
def mock_openshell_session():
    with patch("local_mcp_server.terminal.service.OpenShellTerminalSession") as mock_cls:
        session_instance = MagicMock()
        session_instance.is_alive.return_value = True
        session_instance.read_output.return_value = b"welcome to sandbox\n$ "
        session_instance.exit_code = None
        session_instance.error = None
        mock_cls.return_value = session_instance
        yield session_instance


def test_open_and_list_terminal(mock_openshell_session):
    opened = open_terminal("jupyter-dev", cols=100, rows=30)
    assert opened["sandbox"] == "jupyter-dev"
    assert opened["cols"] == 100
    assert opened["rows"] == 30
    assert opened["status"] == TerminalSessionStatus.ACTIVE.value

    tid = opened["terminal_id"]
    terminals = list_terminals()
    assert any(t["terminal_id"] == tid for t in terminals)


def test_write_and_resize_terminal(mock_openshell_session):
    opened = open_terminal("jupyter-dev")
    tid = opened["terminal_id"]

    res_write = write_terminal(tid, "ls -la\n")
    assert res_write["terminal_id"] == tid
    assert res_write["bytes_written"] > 0
    mock_openshell_session.write.assert_called_with("ls -la\n")

    res_resize = resize_terminal(tid, cols=120, rows=40)
    assert res_resize["cols"] == 120
    assert res_resize["rows"] == 40
    mock_openshell_session.resize.assert_called_with(cols=120, rows=40)


def test_get_terminal_state_and_close(mock_openshell_session):
    opened = open_terminal("jupyter-dev")
    tid = opened["terminal_id"]

    state = get_terminal_state(tid)
    assert "welcome to sandbox" in state["output"]

    closed = close_terminal(tid)
    assert closed["status"] == TerminalSessionStatus.TERMINATED.value
    mock_openshell_session.close.assert_called()

    with pytest.raises(TerminalError, match="not found"):
        write_terminal(tid, "input")


def test_terminal_dimensions_are_bounded(mock_openshell_session):
    with pytest.raises(TerminalError, match="columns must be between"):
        open_terminal("jupyter-dev", cols=1, rows=24)
    opened = open_terminal("jupyter-dev")
    with pytest.raises(TerminalError, match="rows must be between"):
        resize_terminal(opened["terminal_id"], cols=80, rows=1000)


def test_terminal_input_is_bounded(mock_openshell_session):
    opened = open_terminal("jupyter-dev")
    with pytest.raises(TerminalError, match="64 KiB"):
        write_terminal(opened["terminal_id"], "x" * (64 * 1024 + 1))
    mock_openshell_session.write.assert_not_called()
