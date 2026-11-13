"""One login attempt, without any UI.

The window asks Login what to show next. Each call returns a Step:

    Prompt(text, secret)  ask the user and pass the answer to respond()
    Notice(text, error)   show it; call respond(None) to continue
    Started()             the session was started; the greeter should exit
    Failed(text)          authentication failed; start over with begin()
"""

from __future__ import annotations

from dataclasses import dataclass

from .greetd import AuthMessage, Greetd, GreetdError
from .sessions import Session


@dataclass(frozen=True)
class Prompt:
    text: str
    secret: bool


@dataclass(frozen=True)
class Notice:
    text: str
    error: bool


@dataclass(frozen=True)
class Started:
    pass


@dataclass(frozen=True)
class Failed:
    text: str


Step = Prompt | Notice | Started | Failed


class Login:
    def __init__(self, greetd: Greetd, launcher: str):
        self._greetd = greetd
        self._launcher = launcher  # starts an X server and the session (ocimum-x-session)
        self._session: Session | None = None
        self._active = False

    def begin(self, username: str, session: Session) -> Step:
        """Start authenticating `username` for `session`."""
        self.cancel()
        self._session = session
        self._active = True
        return self._advance(lambda: self._greetd.create_session(username))

    def respond(self, answer: str | None) -> Step:
        """Answer the last Prompt (or None after a Notice)."""
        if not self._active:
            raise RuntimeError("no login in progress")
        return self._advance(lambda: self._greetd.post_response(answer))

    def cancel(self) -> None:
        if self._active:
            self._greetd.cancel_session()
            self._active = False

    def _advance(self, request) -> Step:
        try:
            message = request()
        except GreetdError as error:
            self.cancel()
            return Failed(_failure_text(error))
        if message is not None:
            return _step_for(message)
        # Authenticated: start the chosen session.
        assert self._session is not None
        try:
            self._greetd.start_session(
                [self._launcher, self._session.exec], self._session.environment()
            )
        except GreetdError as error:
            self.cancel()
            return Failed(f"Could not start {self._session.name}: {error.description}")
        self._active = False
        return Started()


def _step_for(message: AuthMessage) -> Step:
    if message.needs_response:
        return Prompt(message.text.strip() or "Password:", message.kind == "secret")
    return Notice(message.text.strip(), message.kind == "error")


def _failure_text(error: GreetdError) -> str:
    if error.auth_failed:
        return "Wrong user name or password."
    return error.description
