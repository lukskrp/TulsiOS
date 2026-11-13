from ocimum_greeter.login import Failed, Login, Notice, Prompt, Started
from ocimum_greeter.sessions import Session

from fake_greetd import FakeGreetd

CINNAMON = Session("cinnamon", "Ocimum Desktop", "cinnamon-session-cinnamon", ("X-Cinnamon",))
LAUNCHER = "/run/current-system/sw/bin/ocimum-x-session"


def test_right_password_starts_the_session():
    fake = FakeGreetd(password="foobar")
    login = Login(fake.client, LAUNCHER)
    assert login.begin("alice", CINNAMON) == Prompt("Password:", secret=True)
    assert login.respond("foobar") == Started()
    start = fake.requests[-1]
    assert start == {
        "type": "start_session",
        "cmd": [LAUNCHER, "cinnamon-session-cinnamon"],
        "env": ["XDG_SESSION_TYPE=x11", "XDG_SESSION_DESKTOP=cinnamon", "XDG_CURRENT_DESKTOP=X-Cinnamon"],
    }
    fake.close()


def test_wrong_password_fails_and_cancels_then_a_retry_works():
    fake = FakeGreetd(password="foobar")
    login = Login(fake.client, LAUNCHER)
    login.begin("alice", CINNAMON)
    assert login.respond("wrong") == Failed("Wrong user name or password.")
    # greetd drops the session itself on an auth error; the greeter starts over.
    assert login.begin("alice", CINNAMON) == Prompt("Password:", secret=True)
    assert login.respond("foobar") == Started()
    assert [r["type"] for r in fake.requests].count("create_session") == 2
    fake.close()


def test_info_messages_are_notices_and_need_an_empty_reply():
    fake = FakeGreetd(
        script=[
            {"type": "auth_message", "auth_message_type": "info", "auth_message": "Touch your key"},
            {"type": "auth_message", "auth_message_type": "secret", "auth_message": "PIN: "},
            {"type": "success"},
            {"type": "success"},
        ]
    )
    login = Login(fake.client, LAUNCHER)
    assert login.begin("alice", CINNAMON) == Notice("Touch your key", error=False)
    assert login.respond(None) == Prompt("PIN:", secret=True)
    assert login.respond("1234") == Started()
    assert fake.requests[1] == {"type": "post_auth_message_response", "response": None}
    fake.close()


def test_failed_session_start_is_reported():
    fake = FakeGreetd(
        script=[
            {"type": "success"},
            {"type": "error", "error_type": "error", "description": "no such command"},
            {"type": "success"},
        ]
    )
    login = Login(fake.client, LAUNCHER)
    step = login.begin("alice", CINNAMON)
    assert isinstance(step, Failed) and "no such command" in step.text
    assert fake.requests[-1]["type"] == "cancel_session"
    fake.close()
