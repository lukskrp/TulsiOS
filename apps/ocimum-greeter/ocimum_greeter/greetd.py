"""Client for greetd's IPC protocol.

greetd (https://git.sr.ht/~kennylevinsen/greetd) gives the greeter a Unix socket in
$GREETD_SOCK. Every message is a 32-bit length in native byte order followed by that
many bytes of UTF-8 JSON. Requests and their replies:

    {"type": "create_session", "username": ...}
    {"type": "post_auth_message_response", "response": ... | null}
    {"type": "start_session", "cmd": [...], "env": ["K=V", ...]}
    {"type": "cancel_session"}

Replies are {"type": "success"}, {"type": "error", "error_type": "auth_error" |
"error", "description": ...} or {"type": "auth_message", "auth_message_type":
"visible" | "secret" | "info" | "error", "auth_message": ...}.
"""

from __future__ import annotations

import json
import os
import socket
import struct
from dataclasses import dataclass

_LENGTH = struct.Struct("=I")  # native byte order, as greetd uses


class GreetdError(Exception):
    """greetd answered with an error.

    `auth_failed` is true for a failed authentication (wrong password), which the
    greeter reports to the user and recovers from by starting over.
    """

    def __init__(self, description: str, auth_failed: bool = False):
        super().__init__(description)
        self.description = description
        self.auth_failed = auth_failed


@dataclass(frozen=True)
class AuthMessage:
    """A prompt or notice from PAM, relayed by greetd."""

    kind: str  # "visible", "secret", "info" or "error"
    text: str

    @property
    def needs_response(self) -> bool:
        return self.kind in ("visible", "secret")


class Greetd:
    """A connection to greetd. Each method sends one request and returns
    None (success) or an AuthMessage, or raises GreetdError."""

    def __init__(self, sock: socket.socket):
        self._sock = sock

    @classmethod
    def connect(cls, path: str | None = None) -> "Greetd":
        path = path or os.environ.get("GREETD_SOCK")
        if not path:
            raise GreetdError("GREETD_SOCK is not set: the greeter must be started by greetd")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(path)
        return cls(sock)

    def close(self) -> None:
        self._sock.close()

    # --- requests

    def create_session(self, username: str) -> AuthMessage | None:
        return self._request({"type": "create_session", "username": username})

    def post_response(self, response: str | None) -> AuthMessage | None:
        return self._request({"type": "post_auth_message_response", "response": response})

    def start_session(self, cmd: list[str], env: list[str]) -> None:
        reply = self._request({"type": "start_session", "cmd": cmd, "env": env})
        if reply is not None:
            raise GreetdError(f"unexpected reply to start_session: {reply}")

    def cancel_session(self) -> None:
        try:
            self._request({"type": "cancel_session"})
        except GreetdError:
            pass  # nothing to cancel

    # --- wire format

    def _request(self, message: dict) -> AuthMessage | None:
        send_message(self._sock, message)
        reply = recv_message(self._sock)
        kind = reply.get("type")
        if kind == "success":
            return None
        if kind == "auth_message":
            return AuthMessage(reply.get("auth_message_type", "info"), reply.get("auth_message", ""))
        if kind == "error":
            raise GreetdError(
                reply.get("description", "unknown error"),
                auth_failed=reply.get("error_type") == "auth_error",
            )
        raise GreetdError(f"unexpected reply from greetd: {reply}")


def send_message(sock: socket.socket, message: dict) -> None:
    payload = json.dumps(message).encode("utf-8")
    sock.sendall(_LENGTH.pack(len(payload)) + payload)


def recv_message(sock: socket.socket) -> dict:
    (length,) = _LENGTH.unpack(_recv_exactly(sock, _LENGTH.size))
    return json.loads(_recv_exactly(sock, length).decode("utf-8"))


def _recv_exactly(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise GreetdError("greetd closed the connection")
        data += chunk
    return bytes(data)
