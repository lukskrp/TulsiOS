"""LLM providers. Claude (Anthropic API) is the default; the interface is
small so other providers can be added (see agent.Provider)."""

from __future__ import annotations

import json
import os
from typing import Callable

from .agent import ToolCall, Turn

DEFAULT_MODEL = "claude-opus-5-5"
MODELS = {
    "claude-opus-5-5": "Claude Opus 5.5 (most capable)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (faster)",
    "claude-haiku-5-5": "Claude Haiku 5.5 (fastest, cheapest)",
}
EFFORTS = ("low", "medium", "high")
DEFAULT_EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 64000  # streaming, so a large limit is fine
JSON_RETRIES = 2


class ProviderError(Exception):
    """A problem the user can act on (shown in the window)."""

    def __init__(self, message: str, *, needs_key: bool = False):
        super().__init__(message)
        self.needs_key = needs_key


class ClaudeProvider:
    def __init__(self, api_key: str | None, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT):
        import anthropic

        self.anthropic = anthropic
        # Without a stored key the SDK resolves ANTHROPIC_API_KEY,
        # ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile itself.
        try:
            self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        except anthropic.AnthropicError as e:
            raise ProviderError(f"No Anthropic API key is configured ({e}).", needs_key=True) from e
        self.model = model
        self.effort = effort

    def run_turn(self, system, tools, messages, on_text, on_thinking) -> Turn:
        for attempt in range(JSON_RETRIES + 1):
            try:
                return self._stream(system, tools, messages, on_text, on_thinking)
            except ValueError:
                # A streamed tool input the SDK could not parse at all: the
                # tool_use never completed, so re-issue the turn (bounded).
                if attempt == JSON_RETRIES:
                    raise ProviderError("The model produced an unreadable tool call. Please try again.")
        raise AssertionError("unreachable")

    def _stream(self, system: str, tools: list[dict], messages: list[dict],
                on_text: Callable[[str], None], on_thinking: Callable[[str], None]) -> Turn:
        anthropic = self.anthropic
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": self.effort},
                # The system prompt and tools are fixed per session: cache them.
                cache_control={"type": "ephemeral"},
                # On a policy decline, let the API retry on a suitable model.
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            on_text(event.delta.text)
                        elif event.delta.type == "thinking_delta":
                            on_thinking(event.delta.thinking)
                message = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise ProviderError("The Anthropic API key was rejected. Check it in Settings.", needs_key=True) from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderError(f"This API key may not use {self.model}: {e.message}") from e
        except anthropic.NotFoundError as e:
            raise ProviderError(f"Model {self.model} is not available: {e.message}") from e
        except anthropic.RateLimitError as e:
            raise ProviderError("Rate limited by the Anthropic API. Wait a moment and try again.") from e
        except anthropic.BadRequestError as e:
            raise ProviderError(f"The request was rejected: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"Anthropic API error ({e.status_code}). Try again later.") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("Cannot reach the Anthropic API. Check your internet connection.") from e

        text = "".join(b.text for b in message.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, b.input) for b in message.content if b.type == "tool_use"]
        refusal = ""
        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            refusal = "The model declined this request" + (
                f": {details.explanation}" if details is not None and getattr(details, "explanation", None) else "."
            )
        return Turn(message.content, text, calls, message.stop_reason or "end_turn", refusal)


class FakeProvider:
    """Replays a scripted conversation (tests and demos, no network).

    Script: JSON list of turns, each {"text": str, "tool_calls": [{"name", "input"}]}.
    With `log_path`, each request's messages are appended there as JSON lines.
    """

    def __init__(self, script: list[dict], log_path: str | None = None):
        self.script = list(script)
        self.log_path = log_path
        self.step = 0

    @classmethod
    def from_file(cls, path: str) -> "FakeProvider":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), os.environ.get("OCIMUM_ASSISTANT_FAKE_LOG"))

    def run_turn(self, system, tools, messages, on_text, on_thinking) -> Turn:
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"step": self.step, "messages": messages}, default=str) + "\n")
        if self.step >= len(self.script):
            return Turn([{"type": "text", "text": "(end of script)"}], "(end of script)")
        entry = self.script[self.step]
        self.step += 1
        on_thinking("Considering the request")
        text = entry.get("text", "")
        for word in text.split(" "):
            on_text(word + " ")
        content: list = [{"type": "text", "text": text}] if text else []
        calls = []
        for i, call in enumerate(entry.get("tool_calls", [])):
            call_id = f"toolu_fake_{self.step}_{i}"
            content.append({"type": "tool_use", "id": call_id, "name": call["name"], "input": call["input"]})
            calls.append(ToolCall(call_id, call["name"], call["input"]))
        return Turn(content, text, calls, "tool_use" if calls else "end_turn")


def make_provider(api_key: str | None, model: str, effort: str):
    """OCIMUM_ASSISTANT_PROVIDER=fake:/path/script.json selects the fake provider."""
    spec = os.environ.get("OCIMUM_ASSISTANT_PROVIDER", "")
    if spec.startswith("fake:"):
        return FakeProvider.from_file(spec[len("fake:"):])
    return ClaudeProvider(api_key, model, effort)
