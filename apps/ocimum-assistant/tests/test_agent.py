from dataclasses import dataclass

from ocimum_assistant.agent import (
    Agent,
    ToolCall,
    Turn,
    claim_note,
    describe_outcome,
    describe_tool,
    to_provider_tools,
)
from ocimum_assistant.providers import FakeProvider


@dataclass
class Result:
    text: str
    is_error: bool
    structured: dict | None = None


class FakeTools:
    def __init__(self, fail: bool = False, receipts: dict | None = None):
        self.calls = []
        self.fail = fail
        self.receipts = receipts or {}

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.fail:
            raise RuntimeError("tulsi-mcp went away")
        receipt = self.receipts.get(name)
        return Result(f"{name} ok", False, {"receipt": receipt} if receipt else None)


class Events:
    def __init__(self):
        self.log = []

    def text(self, d): self.log.append(("text", d))
    def thinking(self, d): self.log.append(("thinking", d))
    def turn_done(self, t): self.log.append(("done", t))
    def tool_started(self, n, a): self.log.append(("start", n))
    def tool_finished(self, n, ok, t): self.log.append(("finish", n, ok))
    def notice(self, t): self.log.append(("notice", t))
    def outcome(self, receipts, note): self.log.append(("outcome", receipts, note))


class ScriptedTurns:
    """Provider returning given Turn objects in order."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.seen = []

    def run_turn(self, system, tools, messages, on_text, on_thinking):
        self.seen.append([dict(m) for m in messages])
        return self.turns.pop(0)


def test_tool_loop_pairs_every_tool_use_with_a_result():
    provider = FakeProvider([
        {"text": "Let me look.", "tool_calls": [
            {"name": "search_packages", "input": {"query": "vlc"}},
            {"name": "get_state", "input": {}},
        ]},
        {"text": "VLC is available."},
    ])
    tools, events = FakeTools(), Events()
    agent = Agent(provider, tools, [], "server notes")
    agent.ask("find vlc", events)

    assert [c[0] for c in tools.calls] == ["search_packages", "get_state"]
    roles = [m["role"] for m in agent.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    results = agent.messages[2]["content"]
    ids = [b["id"] for b in agent.messages[1]["content"] if b["type"] == "tool_use"]
    assert [r["tool_use_id"] for r in results] == ids
    assert all(r["is_error"] is False for r in results)
    assert ("done", "VLC is available.") in events.log
    assert "server notes" in agent.system


def test_truncated_tool_input_is_never_run():
    turn = Turn([{"type": "tool_use", "id": "t1", "name": "apply_change", "input": {"operations": []}}],
                "", [ToolCall("t1", "apply_change", {"operations": []})], "max_tokens")
    provider = ScriptedTurns(turn, Turn([], "ok"))
    tools = FakeTools()
    agent = Agent(provider, tools, [])
    agent.ask("do it", Events())
    assert tools.calls == []
    result = agent.messages[2]["content"][0]
    assert result["is_error"] is True and "cut off" in result["content"]


def test_invalid_input_and_tool_failure_become_error_results():
    turn = Turn([], "", [ToolCall("a", "x", "not a dict"), ToolCall("b", "get_state", {})], "tool_use")
    agent = Agent(ScriptedTurns(turn, Turn([], "done")), FakeTools(fail=True), [])
    events = Events()
    agent.ask("go", events)
    results = agent.messages[2]["content"]
    assert results[0]["is_error"] and "INVALID_JSON" in results[0]["content"]
    assert results[1]["is_error"] and "could not run" in results[1]["content"]
    assert ("finish", "get_state", False) in events.log


def test_refusal_stops_and_tells_the_user():
    refusal = Turn([], "", [], "refusal", "The model declined this request.")
    agent = Agent(ScriptedTurns(refusal), FakeTools(), [])
    events = Events()
    agent.ask("bad", events)
    assert ("notice", "The model declined this request.") in events.log


def test_cancel_still_answers_pending_tool_calls():
    turn = Turn([], "", [ToolCall("a", "get_state", {})], "tool_use")
    agent = Agent(ScriptedTurns(turn), FakeTools(), [])
    events = Events()

    class Cancelling(Events):
        def tool_started(self, n, a):
            raise AssertionError("must not start after cancel")

    agent.provider = ScriptedTurns(turn)
    original = agent.provider.run_turn

    def run_and_cancel(*args):
        t = original(*args)
        agent.cancelled = True
        return t

    agent.provider.run_turn = run_and_cancel
    agent.ask("go", Cancelling())
    assert agent.messages[-1]["content"][0]["is_error"] is True
    assert "stopped" in agent.messages[-1]["content"][0]["content"]


def test_pause_turn_continues_without_tool_results():
    agent = Agent(ScriptedTurns(Turn([], "", [], "pause_turn"), Turn([], "finished")), FakeTools(), [])
    agent.ask("go", Events())
    assert [m["role"] for m in agent.messages] == ["user", "assistant", "assistant"]


def test_tool_definitions_and_descriptions():
    defs = to_provider_tools([{"name": "get_state", "description": "d", "inputSchema": {"type": "object"}}])
    assert defs == [{"name": "get_state", "description": "d", "input_schema": {"type": "object"},
                     "eager_input_streaming": True}]
    assert describe_tool("apply_change", {"operations": [
        {"op": "addPackage", "name": "vlc"}, {"op": "setService", "name": "printing", "enable": True}]}) == (
        "Changing: install vlc, enable service printing")
    assert describe_tool("search_packages", {"query": "gimp"}) == "Searching packages for “gimp”"


APPLIED = {"tool": "apply_change", "outcome": "applied", "approved_via": "Starah (the agent's level)",
           "changes": ["+ package vlc"], "commit": "abc1234"}


def test_receipts_decide_the_outcome_not_the_reply():
    provider = FakeProvider([
        {"text": "Installing.", "tool_calls": [
            {"name": "apply_change", "input": {"operations": [{"op": "addPackage", "name": "vlc"}],
                                               "reason": "asked"}},
        ]},
        {"text": "Done: VLC is installed."},
    ])
    events = Events()
    Agent(provider, FakeTools(receipts={"apply_change": APPLIED}), []).ask("vlc", events)
    assert events.log[-1] == ("outcome", [APPLIED], "")
    kind, text = describe_outcome([APPLIED])
    assert kind == "changed"
    assert text == "Changed: + package vlc · done on its own"


def test_a_claimed_change_without_a_receipt_gets_a_note():
    provider = FakeProvider([{"text": "I have installed VLC for you."}])
    events = Events()
    Agent(provider, FakeTools(), []).ask("vlc", events)
    assert events.log[-1] == ("outcome", [], "Nothing on your system was changed in this reply.")


def test_claim_note_is_conservative():
    assert claim_note("VLC is already installed.", []) == ""
    assert claim_note("I can install VLC if you like.", []) == ""
    assert claim_note("Should I enable printing?", []) == ""
    assert claim_note("It wasn't installed.", []) == ""
    assert claim_note("Printing is enabled now.", []) != ""
    assert claim_note("Printing is enabled now.", [APPLIED]) == ""


def test_outcome_kinds():
    assert describe_outcome([]) == ("", "")
    assert describe_outcome([{"outcome": "rejected"}])[0] == "rejected"
    assert describe_outcome([{"outcome": "rolled_back"}])[0] == "rolled_back"
    assert describe_outcome([{"outcome": "nothing"}])[0] == "nothing"
    by_you = dict(APPLIED, approved_via="desktop dialog")
    assert describe_outcome([by_you])[1].endswith("approved by you")


def test_outcome_is_reported_even_when_the_provider_fails():
    class Broken:
        def run_turn(self, *args):
            raise RuntimeError("network down")

    events = Events()
    try:
        Agent(Broken(), FakeTools(), []).ask("vlc", events)
    except RuntimeError:
        pass
    assert events.log[-1] == ("outcome", [], "")


def test_undo_outside_the_conversation_is_told_to_the_model():
    provider = ScriptedTurns(Turn([], "ok"))
    agent = Agent(provider, FakeTools(), [])
    agent.pending_notes.append("the user pressed Undo.")
    agent.ask("what now?", Events())
    first = provider.seen[0][0]["content"]
    assert first.startswith("(Since your last reply: the user pressed Undo.)")
    assert first.endswith("what now?")
    assert agent.pending_notes == []
