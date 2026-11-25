import json

from ocimum_nix_editor import lsp


def frames(data: bytes) -> list[dict]:
    return lsp.Decoder().feed(data)


def test_framing_round_trips_in_pieces():
    one = lsp.encode({"jsonrpc": "2.0", "id": 1, "result": {"é": "ü"}})
    two = lsp.encode({"jsonrpc": "2.0", "method": "x", "params": {}})
    decoder = lsp.Decoder()
    got = []
    data = one + two
    for i in range(0, len(data), 7):  # arrives in small pieces
        got += decoder.feed(data[i:i + 7])
    assert [m.get("id") for m in got] == [1, None]
    assert got[0]["result"] == {"é": "ü"}
    assert decoder.buffer == b""


def test_utf16_columns():
    line = "a😀b"  # the emoji is two UTF-16 units
    assert lsp.chars_to_utf16(line, 2) == 3
    assert lsp.utf16_to_chars(line, 3) == 2
    assert lsp.utf16_to_chars(line, 99) == 3


class FakeServer:
    def __init__(self):
        self.sent: list[dict] = []

    def write(self, data: bytes) -> None:
        self.sent += frames(data)


def test_nothing_but_initialize_goes_out_before_the_server_is_ready():
    server = FakeServer()
    client = lsp.Client(server.write, nixpkgs="/etc/tulsi/nixpkgs", log=lambda _t: None)
    ready = []
    client.on_ready = lambda: ready.append(True)
    client.initialize()
    client.did_open("/tmp/a.nix", "{ }")
    assert [m.get("method") for m in server.sent] == ["initialize"]
    init = server.sent[0]
    assert init["params"]["initializationOptions"]["nixpkgs"]["expr"] == "import /etc/tulsi/nixpkgs { }"
    assert init["params"]["capabilities"]["workspace"]["configuration"] is True

    client.feed(lsp.encode({"jsonrpc": "2.0", "id": init["id"], "result": {"capabilities": {}}}))
    assert ready == [True]
    assert [m.get("method") for m in server.sent[1:]] == [
        "initialized", "workspace/didChangeConfiguration", "textDocument/didOpen"]
    opened = server.sent[-1]["params"]["textDocument"]
    assert opened["uri"] == "file:///tmp/a.nix" and opened["languageId"] == "nix"


def ready_client():
    server = FakeServer()
    client = lsp.Client(server.write, nixpkgs="/n", log=lambda _t: None)
    client.initialize()
    client.feed(lsp.encode({"jsonrpc": "2.0", "id": 1, "result": {}}))
    server.sent.clear()
    return server, client


def test_the_server_asks_for_its_settings():
    server, client = ready_client()
    client.feed(lsp.encode({"jsonrpc": "2.0", "id": 7, "method": "workspace/configuration",
                            "params": {"items": [{"section": "nixd"}, {"section": "other"}]}}))
    reply = server.sent[-1]
    assert reply["id"] == 7
    assert reply["result"][0]["nixpkgs"]["expr"] == "import /n { }"
    assert reply["result"][1] is None


def test_changes_versions_and_diagnostics():
    server, client = ready_client()
    client.did_open("/tmp/a.nix", "x")
    client.did_change("/tmp/a.nix", "xy")
    change = server.sent[-1]["params"]
    assert change["textDocument"]["version"] == 2 and change["contentChanges"] == [{"text": "xy"}]
    seen = []
    client.on_diagnostics = lambda uri, d: seen.append((uri, d))
    client.feed(lsp.encode({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                            "params": {"uri": "file:///tmp/a.nix", "diagnostics": [{"message": "m"}]}}))
    assert seen == [("file:///tmp/a.nix", [{"message": "m"}])]


def test_completion_and_hover_replies():
    server, client = ready_client()
    got = {}
    rid = client.completion("/tmp/a.nix", 3, 26, lambda items: got.update(items=items))
    assert server.sent[-1]["params"]["position"] == {"line": 3, "character": 26}
    client.feed(lsp.encode({"jsonrpc": "2.0", "id": rid, "result": {"isIncomplete": False, "items": [
        {"label": "hello", "detail": "pkg"},
        {"label": "helix", "textEdit": {"newText": "helix", "range": {}},
         "documentation": {"kind": "markdown", "value": "An editor"}}]}}))
    assert got["items"] == [
        {"label": "hello", "text": "hello", "detail": "pkg", "doc": ""},
        {"label": "helix", "text": "helix", "detail": "", "doc": "An editor"}]

    rid = client.hover("/tmp/a.nix", 1, 9, lambda text: got.update(hover=text))
    client.feed(lsp.encode({"jsonrpc": "2.0", "id": rid, "result": {
        "contents": {"kind": "markdown", "value": "`hello-2.12.3`\n## Description"}}}))
    assert got["hover"].startswith("`hello-2.12.3`")

    rid = client.hover("/tmp/a.nix", 1, 1, lambda text: got.update(none=text))
    client.feed(lsp.encode({"jsonrpc": "2.0", "id": rid, "result": None}))
    assert got["none"] == ""


def test_an_error_reply_still_calls_back():
    server, client = ready_client()
    got = []
    rid = client.hover("/tmp/a.nix", 0, 0, got.append)
    client.feed(lsp.encode({"jsonrpc": "2.0", "id": rid, "error": {"code": -1, "message": "no"}}))
    assert got == [""]


def test_settings_are_json():
    json.dumps(lsp.settings())
