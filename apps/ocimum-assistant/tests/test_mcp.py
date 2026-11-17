import sys
from pathlib import Path

import pytest

from ocimum_assistant.mcp import McpClient, McpError

SERVER = [sys.executable, str(Path(__file__).with_name("fake_mcp_server.py"))]


@pytest.fixture
def client():
    c = McpClient(SERVER)
    c.start()
    yield c
    c.close()


def test_handshake_and_tools(client):
    assert client.server_name == "fake"
    assert client.instructions == "be careful"
    assert [t["name"] for t in client.list_tools()] == ["echo"]


def test_call_tool_survives_server_requests_and_noise(client):
    result = client.call_tool("echo", {"x": 1})
    assert result.text == '{"x": 1}' and result.is_error is False
    assert client.call_tool("echo", {"tool_error": True}).is_error is True
    assert result.structured is None


def test_structured_content_is_kept(client):
    result = client.call_tool("echo", {"receipt": {"outcome": "applied"}})
    assert result.structured == {"receipt": {"outcome": "applied"}}


def test_protocol_errors_raise(client):
    with pytest.raises(McpError, match="bad args"):
        client.call_tool("echo", {"fail": True})


def test_missing_server_binary():
    with pytest.raises(McpError, match="cannot start"):
        McpClient(["/nonexistent/tulsi-mcp"]).start()


def test_command_string_is_split():
    assert McpClient("tulsi-mcp --approver /bin/true").argv == ["tulsi-mcp", "--approver", "/bin/true"]
