"""The real ClaudeProvider + anthropic SDK against a local stand-in API server.

Checks the request the app sends and how a streamed response (thinking,
text, a streamed tool call) is turned into a Turn. No network, no API key.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

anthropic = pytest.importorskip("anthropic")

from ocimum_assistant.providers import FALLBACK_BETA, ClaudeProvider, ProviderError  # noqa: E402


def sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


STREAM = sse([
    {"type": "message_start", "message": {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 1}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "User wants a player."}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig123"}},
    {"type": "content_block_stop", "index": 0},
    {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Searching "}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "now."}},
    {"type": "content_block_stop", "index": 1},
    {"type": "content_block_start", "index": 2, "content_block": {
        "type": "tool_use", "id": "toolu_1", "name": "search_packages", "input": {}}},
    {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": "{\"query\": "}},
    {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": "\"video player\"}"}},
    {"type": "content_block_stop", "index": 2},
    {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 30}},
    {"type": "message_stop"},
])


class Server:
    def __init__(self, status=200, body=STREAM, content_type="text/event-stream"):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", 0))
                outer.requests.append({"path": self.path, "headers": dict(self.headers),
                                       "body": json.loads(self.rfile.read(length))})
                self.send_response(status)
                self.send_header("content-type", content_type)
                self.send_header("request-id", "req_test")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def api(monkeypatch):
    servers = []

    def start(**kwargs):
        s = Server(**kwargs)
        servers.append(s)
        monkeypatch.setenv("ANTHROPIC_BASE_URL", s.url)
        return s

    yield start
    for s in servers:
        s.close()


TOOLS = [{"name": "search_packages", "description": "search", "eager_input_streaming": True,
          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}]


def test_streamed_turn_and_request_shape(api):
    server = api()
    provider = ClaudeProvider("sk-test", "claude-opus-5-5", "medium")
    texts, thoughts = [], []
    turn = provider.run_turn("SYSTEM", TOOLS, [{"role": "user", "content": "video player?"}],
                             texts.append, thoughts.append)

    assert "".join(texts) == "Searching now."
    assert thoughts == ["User wants a player."]
    assert turn.text == "Searching now."
    assert turn.stop_reason == "tool_use"
    assert [(c.id, c.name, c.input) for c in turn.tool_calls] == [("toolu_1", "search_packages", {"query": "video player"})]
    # Thinking block (with its signature) is kept for the next request.
    assert turn.content[0].type == "thinking" and turn.content[0].signature == "sig123"

    req = server.requests[0]
    body, headers = req["body"], {k.lower(): v for k, v in req["headers"].items()}
    assert req["path"].startswith("/v1/messages")
    assert body["model"] == "claude-opus-5-5"
    assert body["stream"] is True
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert body["output_config"] == {"effort": "medium"}
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default"
    assert body["tools"][0]["eager_input_streaming"] is True
    assert FALLBACK_BETA in headers.get("anthropic-beta", "")
    assert headers["x-api-key"] == "sk-test"


def test_history_with_thinking_blocks_can_be_sent_back(api):
    server = api()
    provider = ClaudeProvider("sk-test")
    turn = provider.run_turn("S", TOOLS, [{"role": "user", "content": "hi"}], lambda _: None, lambda _: None)
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": turn.content},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "vlc"}]},
    ]
    provider.run_turn("S", TOOLS, history, lambda _: None, lambda _: None)
    sent = server.requests[1]["body"]["messages"][1]["content"]
    assert sent[0]["type"] == "thinking" and sent[0]["signature"] == "sig123"
    assert sent[2]["type"] == "tool_use" and sent[2]["input"] == {"query": "video player"}


def test_rejected_key_asks_for_a_new_one(api):
    api(status=401, content_type="application/json",
        body=json.dumps({"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}).encode())
    provider = ClaudeProvider("sk-wrong")
    with pytest.raises(ProviderError) as err:
        provider.run_turn("S", [], [{"role": "user", "content": "hi"}], lambda _: None, lambda _: None)
    assert err.value.needs_key


def test_refusal_is_reported(api):
    body = sse([
        {"type": "message_start", "message": {
            "id": "msg_2", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 5, "output_tokens": 1}}},
        {"type": "message_delta", "delta": {"stop_reason": "refusal", "stop_sequence": None,
                                            "stop_details": {"type": "refusal", "category": None, "explanation": "Not allowed."}},
         "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ])
    api(body=body)
    turn = ClaudeProvider("sk-test").run_turn("S", [], [{"role": "user", "content": "x"}], lambda _: None, lambda _: None)
    assert turn.stop_reason == "refusal"
    assert turn.refusal.startswith("The model declined this request")
