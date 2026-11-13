import socket
import struct

import pytest

from ocimum_greeter.greetd import AuthMessage, GreetdError, recv_message, send_message

from fake_greetd import FakeGreetd


def test_wire_format_is_native_length_then_json():
    a, b = socket.socketpair()
    send_message(a, {"type": "create_session", "username": "alice"})
    (length,) = struct.unpack("=I", b.recv(4))
    assert b.recv(length) == b'{"type": "create_session", "username": "alice"}'
    a.close()
    b.close()


def test_messages_round_trip_across_partial_reads():
    a, b = socket.socketpair()
    message = {"type": "start_session", "cmd": ["x" * 5000], "env": ["A=B"]}
    send_message(a, message)
    assert recv_message(b) == message
    a.close()
    b.close()


def test_replies_map_to_results_and_errors():
    fake = FakeGreetd(
        script=[
            {"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password: "},
            {"type": "error", "error_type": "auth_error", "description": "nope"},
            {"type": "error", "error_type": "error", "description": "broken"},
            {"type": "success"},
        ]
    )
    assert fake.client.create_session("alice") == AuthMessage("secret", "Password: ")
    with pytest.raises(GreetdError) as auth:
        fake.client.post_response("wrong")
    assert auth.value.auth_failed
    with pytest.raises(GreetdError) as other:
        fake.client.post_response("x")
    assert not other.value.auth_failed and other.value.description == "broken"
    assert fake.client.start_session(["cmd"], []) is None
    assert [r["type"] for r in fake.requests] == [
        "create_session",
        "post_auth_message_response",
        "post_auth_message_response",
        "start_session",
    ]
    fake.close()


def test_connect_needs_greetd_sock(monkeypatch):
    from ocimum_greeter.greetd import Greetd

    monkeypatch.delenv("GREETD_SOCK", raising=False)
    with pytest.raises(GreetdError):
        Greetd.connect()
