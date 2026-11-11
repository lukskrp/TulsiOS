import json

import pytest

from ocimum_software_center.approve import INVALID, main, parse_request


def test_parse_valid_request():
    req = parse_request(json.dumps({
        "title": "An AI agent wants to change this system",
        "reason": "user asked",
        "changes": ["+ package vlc"],
        "requester": "agent",
    }))
    assert req["changes"] == ["+ package vlc"]
    assert req["diff"] is None


def test_defaults_for_missing_fields():
    req = parse_request('{"changes": ["x"]}')
    assert req["reason"] == "(no reason given)"
    assert req["requester"] == "an unknown program"


@pytest.mark.parametrize("bad", ["", "[]", '{"changes": []}', '{"changes": [1]}', '{"title": "x"}'])
def test_rejects_invalid_requests(bad):
    with pytest.raises(ValueError):
        parse_request(bad)


def test_invalid_input_exits_without_a_dialog(monkeypatch, capsys):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("nonsense"))
    assert main() == INVALID
    assert "invalid request" in capsys.readouterr().err
