"""The agent loop: model turn -> tulsi-mcp tool calls -> results -> repeat.

GTK-free and provider-neutral so it can be tested with a scripted provider.
Messages use the Anthropic Messages format; assistant turns are appended
exactly as the provider returned them (thinking blocks must be passed back
unchanged).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

MAX_STEPS = 25

SYSTEM_PROMPT = """\
You are the Ocimum Assistant, built into TulsiOS, a NixOS-based desktop system. You help \
the user change their system in plain language: install or remove software, add browser \
extensions, turn services on or off, and edit their NixOS configuration.

How to work:
- Use the TulsiOS tools for everything; you have no shell. Find package names with \
search_packages before installing; never guess attribute names.
- Before a change, say briefly what you are about to do. Changes are shown to the user in \
an approval dialog; if they reject one, accept that and ask what they would prefer.
- Prefer apply_change (packages, browser extensions, service toggles). Edit \
configuration.nix only for settings those cannot express: read_configuration first, keep \
everything the user wrote, and pass the complete file.
- Rebuilds can take minutes. If one fails, it was rolled back automatically: explain the \
error in plain words and propose a fix.
- Answer in short, plain sentences for someone who does not know Nix. Use Markdown \
sparingly (bold, lists, inline code).

Notes from the TulsiOS tool server:
"""


@dataclass
class ToolCall:
    id: str
    name: str
    input: Any


@dataclass
class Turn:
    """One model response."""

    content: list  # provider-native blocks, appended to history unchanged
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    refusal: str = ""


class Provider(Protocol):
    def run_turn(
        self,
        system: str,
        tools: list[dict],
        messages: list[dict],
        on_text: Callable[[str], None],
        on_thinking: Callable[[str], None],
    ) -> Turn: ...


class Tools(Protocol):
    def call_tool(self, name: str, arguments: dict) -> Any: ...


class Events(Protocol):
    """What the UI hears about. Called from the worker thread."""

    def text(self, delta: str) -> None: ...
    def thinking(self, delta: str) -> None: ...
    def turn_done(self, text: str) -> None: ...
    def tool_started(self, name: str, arguments: dict) -> None: ...
    def tool_finished(self, name: str, ok: bool, text: str) -> None: ...
    def notice(self, text: str) -> None: ...


def to_provider_tools(mcp_tools: list[dict]) -> list[dict]:
    """MCP tool definitions -> Messages API tool definitions (order kept for caching)."""
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}},
            # configuration edits carry a whole file; stream it as it is written
            "eager_input_streaming": True,
        }
        for t in mcp_tools
    ]


class Agent:
    def __init__(self, provider: Provider, tools: Tools, tool_defs: list[dict], instructions: str = ""):
        self.provider = provider
        self.tools = tools
        self.tool_defs = tool_defs
        self.system = SYSTEM_PROMPT + (instructions.strip() or "(none)")
        self.messages: list[dict] = []
        self.cancelled = False

    def reset(self) -> None:
        self.messages = []

    def ask(self, text: str, events: Events) -> None:
        """Runs until the model stops calling tools. Blocking."""
        self.cancelled = False
        self.messages.append({"role": "user", "content": text})
        for _ in range(MAX_STEPS):
            if self.cancelled:
                events.notice("Stopped.")
                return
            turn = self.provider.run_turn(
                self.system, self.tool_defs, self.messages, events.text, events.thinking
            )
            self.messages.append({"role": "assistant", "content": turn.content})
            events.turn_done(turn.text)

            if turn.stop_reason == "refusal":
                events.notice(turn.refusal or "The model declined this request.")
                return
            if turn.stop_reason == "pause_turn":
                continue
            if not turn.tool_calls:
                if turn.stop_reason == "max_tokens":
                    events.notice("The answer was cut off because it got too long.")
                return

            # Every tool_use needs a matching tool_result in one user message.
            results = [self._run(call, turn.stop_reason, events) for call in turn.tool_calls]
            self.messages.append({"role": "user", "content": results})
        events.notice("Stopped after too many steps; ask again to continue.")

    def _run(self, call: ToolCall, stop_reason: str, events: Events) -> dict:
        def result(text: str, error: bool) -> dict:
            return {"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": error}

        # A tool input cut off by max_tokens parses as a valid but partial
        # object: never run it.
        if stop_reason == "max_tokens":
            return result("Your tool input was cut off (output limit). Make a smaller change.", True)
        if not isinstance(call.input, dict):
            return result(json.dumps({"INVALID_JSON": str(call.input)}), True)
        if self.cancelled:
            return result("The user stopped the assistant before this ran.", True)

        events.tool_started(call.name, call.input)
        try:
            outcome = self.tools.call_tool(call.name, call.input)
            text, ok = outcome.text, not outcome.is_error
        except Exception as e:  # noqa: BLE001 - report any tool failure to the model
            text, ok = f"The tool could not run: {e}", False
        events.tool_finished(call.name, ok, text)
        return result(text, not ok)


def describe_tool(name: str, arguments: dict) -> str:
    """Short human description of a tool call for the chat."""
    ops = arguments.get("operations") or []
    words = {
        "addPackage": "install {name}", "removePackage": "remove {name}",
        "addExtension": "add {browser} extension {id}", "removeExtension": "remove {browser} extension {id}",
    }
    def op_text(op: dict) -> str:
        if op.get("op") == "setService":
            return f"{'enable' if op.get('enable') else 'disable'} service {op.get('name', '?')}"
        template = words.get(op.get("op", ""), op.get("op", "change"))
        try:
            return template.format(**{k: op.get(k, "?") for k in ("name", "browser", "id")})
        except (KeyError, IndexError):
            return template
    if name == "search_packages":
        return f"Searching packages for “{arguments.get('query', '')}”"
    if name in ("plan_change", "apply_change"):
        verb = "Planning" if name == "plan_change" else "Asking you to approve"
        return f"{verb}: " + ", ".join(op_text(o) for o in ops if isinstance(o, dict))
    if name == "apply_configuration_edit":
        return f"Asking you to approve a configuration edit: {arguments.get('summary', '')}"
    return {
        "package_info": f"Looking up {arguments.get('attr', 'a package')}",
        "get_state": "Checking what is installed",
        "read_configuration": "Reading your configuration",
        "history": "Checking recent changes",
        "propose_configuration_edit": "Checking a configuration edit",
        "undo_last_change": "Asking you to approve undoing the latest change",
    }.get(name, f"Using {name}")
