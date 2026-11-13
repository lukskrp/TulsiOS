"""A scripted greetd on one end of a socketpair, for the tests."""

from __future__ import annotations

import socket
import threading

from ocimum_greeter.greetd import Greetd, recv_message, send_message


class FakeGreetd:
    """Answers each request with the next scripted reply and records the requests.

    `password` makes it behave like greetd with PAM's usual password prompt:
    create_session → secret prompt, then success for the right password and an
    auth_error otherwise.
    """

    def __init__(self, password: str | None = None, script: list[dict] | None = None):
        self.requests: list[dict] = []
        self._password = password
        self._script = list(script or [])
        client, self._server = socket.socketpair()
        self.client = Greetd(client)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _reply(self, request: dict) -> dict:
        if self._script:
            return self._script.pop(0)
        kind = request["type"]
        if kind == "create_session":
            return {"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password: "}
        if kind == "post_auth_message_response":
            if request["response"] == self._password:
                return {"type": "success"}
            return {"type": "error", "error_type": "auth_error", "description": "pam_authenticate failed"}
        return {"type": "success"}

    def _serve(self) -> None:
        try:
            while True:
                request = recv_message(self._server)
                self.requests.append(request)
                send_message(self._server, self._reply(request))
        except Exception:
            pass

    def close(self) -> None:
        self.client.close()
        self._server.close()
