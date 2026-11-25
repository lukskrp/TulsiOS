"""A small Language Server Protocol client for nixd (ADR 0019).

Only what the editor uses: initialize, didOpen, didChange (the whole text), didSave,
completion, hover, publishDiagnostics, and answering nixd's `workspace/configuration`
requests with TulsiOS's settings.

`Client` is transport-agnostic: it is given a `write(bytes)` function and fed what the
server prints (`feed(bytes)`). `GioTransport` runs the server with Gio.Subprocess and
drives both from the GLib main loop, with no threads.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Callable

# The system's pinned nixpkgs, the one Recipes and `tulsi recipe build-draft` build
# against, so completion offers what will build. Overridable for tests.
NIXPKGS = os.environ.get("TULSI_NIXPKGS", "/etc/tulsi/nixpkgs")


def settings(nixpkgs: str = NIXPKGS) -> dict:
    """nixd's settings. NixOS options are not completed: TulsiOS keeps the system's
    configuration in state.json, and people write packages, not configuration.nix."""
    return {
        "nixpkgs": {"expr": f"import {nixpkgs} {{ }}"},
        "diagnostic": {"suppress": []},
    }


# ---------------------------------------------------------------- framing


def encode(message: dict) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: %d\r\n\r\n" % len(body) + body


class Decoder:
    """Splits the server's output into messages (`Content-Length` framing)."""

    def __init__(self) -> None:
        self.buffer = b""

    def feed(self, data: bytes) -> list[dict]:
        self.buffer += data
        messages = []
        while True:
            end = self.buffer.find(b"\r\n\r\n")
            if end < 0:
                break
            length = None
            for line in self.buffer[:end].split(b"\r\n"):
                name, _, value = line.partition(b":")
                if name.strip().lower() == b"content-length":
                    length = int(value.strip())
            if length is None:  # not a header: skip to the next one
                self.buffer = self.buffer[end + 4:]
                continue
            start = end + 4
            if len(self.buffer) < start + length:
                break
            body = self.buffer[start:start + length]
            self.buffer = self.buffer[start + length:]
            try:
                messages.append(json.loads(body))
            except ValueError:
                continue
        return messages


# ------------------------------------------------------------- positions
# LSP counts characters in UTF-16 code units; GtkTextIter counts code points.


def utf16_to_chars(line: str, units: int) -> int:
    count = 0
    for i, ch in enumerate(line):
        if count >= units:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(line)


def chars_to_utf16(line: str, chars: int) -> int:
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in line[:chars])


def file_uri(path: str) -> str:
    from urllib.parse import quote

    return "file://" + quote(os.path.abspath(path))


# ----------------------------------------------------------- hover text


def hover_text(result) -> str:
    """The plain text of a hover reply (MarkupContent, MarkedString or a list)."""
    if not result:
        return ""
    contents = result.get("contents") if isinstance(result, dict) else result
    if isinstance(contents, str):
        return contents.strip()
    if isinstance(contents, dict):
        return str(contents.get("value", "")).strip()
    if isinstance(contents, list):
        return "\n\n".join(hover_text({"contents": c}) for c in contents).strip()
    return ""


def completion_items(result) -> list[dict]:
    """[{label, text, detail, doc}] from a completion reply (a list or CompletionList)."""
    if not result:
        return []
    items = result.get("items", []) if isinstance(result, dict) else result
    out = []
    for it in items:
        label = it.get("label", "")
        text = it.get("insertText") or label
        edit = it.get("textEdit")
        if isinstance(edit, dict) and edit.get("newText"):
            text = edit["newText"]
        doc = it.get("documentation", "")
        if isinstance(doc, dict):
            doc = doc.get("value", "")
        out.append({"label": label, "text": text, "detail": it.get("detail", "") or "",
                    "doc": doc or ""})
    return out


# ---------------------------------------------------------------- client


class Client:
    def __init__(self, write: Callable[[bytes], None], root: str = "",
                 nixpkgs: str = NIXPKGS, log: Callable[[str], None] | None = None):
        self._write = write
        self.decoder = Decoder()
        self.next_id = 1
        self.pending: dict[int, Callable] = {}
        self.versions: dict[str, int] = {}
        self.ready = False
        self.queued: list[dict] = []
        self.settings = settings(nixpkgs)
        self.log = log or (lambda text: print(f"nix-editor: lsp: {text}", file=sys.stderr, flush=True))
        # Set by the editor.
        self.on_diagnostics: Callable[[str, list], None] = lambda uri, diags: None
        self.on_ready: Callable[[], None] = lambda: None
        self.root = root

    # -- sending

    def send(self, message: dict) -> None:
        message["jsonrpc"] = "2.0"
        # Until the server answered `initialize`, only that may be sent.
        if not self.ready and message.get("method") not in ("initialize",) and "result" not in message:
            self.queued.append(message)
            return
        self._write(encode(message))

    def request(self, method: str, params: dict, on_result: Callable | None = None) -> int:
        rid = self.next_id
        self.next_id += 1
        if on_result:
            self.pending[rid] = on_result
        self.send({"id": rid, "method": method, "params": params})
        return rid

    def notify(self, method: str, params: dict) -> None:
        self.send({"method": method, "params": params})

    def initialize(self) -> None:
        params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "ocimum-nix-editor"},
            "rootUri": file_uri(self.root) if self.root else None,
            "initializationOptions": self.settings,
            "capabilities": {
                "workspace": {"configuration": True},
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "completion": {"completionItem": {"snippetSupport": False,
                                                       "documentationFormat": ["plaintext", "markdown"]}},
                    "hover": {"contentFormat": ["plaintext", "markdown"]},
                    "publishDiagnostics": {},
                },
            },
        }
        self.request("initialize", params, self._initialized)

    def _initialized(self, _result) -> None:
        self.ready = True
        self._write(encode({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
        self._write(encode({"jsonrpc": "2.0", "method": "workspace/didChangeConfiguration",
                            "params": {"settings": {"nixd": self.settings}}}))
        queued, self.queued = self.queued, []
        for m in queued:
            self._write(encode(m))
        self.log("ready")
        self.on_ready()

    # -- documents

    def did_open(self, path: str, text: str) -> None:
        uri = file_uri(path)
        self.versions[uri] = 1
        self.notify("textDocument/didOpen", {"textDocument": {
            "uri": uri, "languageId": "nix", "version": 1, "text": text}})

    def did_change(self, path: str, text: str) -> None:
        uri = file_uri(path)
        self.versions[uri] = self.versions.get(uri, 1) + 1
        self.notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": self.versions[uri]},
            "contentChanges": [{"text": text}]})

    def did_save(self, path: str) -> None:
        self.notify("textDocument/didSave", {"textDocument": {"uri": file_uri(path)}})

    def did_close(self, path: str) -> None:
        uri = file_uri(path)
        self.versions.pop(uri, None)
        self.notify("textDocument/didClose", {"textDocument": {"uri": uri}})

    def completion(self, path: str, line: int, character: int, on_items: Callable[[list], None]) -> int:
        return self.request("textDocument/completion", {
            "textDocument": {"uri": file_uri(path)},
            "position": {"line": line, "character": character}},
            lambda result: on_items(completion_items(result)))

    def hover(self, path: str, line: int, character: int, on_text: Callable[[str], None]) -> int:
        return self.request("textDocument/hover", {
            "textDocument": {"uri": file_uri(path)},
            "position": {"line": line, "character": character}},
            lambda result: on_text(hover_text(result)))

    def shutdown(self) -> None:
        if self.ready:
            self._write(encode({"jsonrpc": "2.0", "id": self.next_id, "method": "shutdown"}))
            self._write(encode({"jsonrpc": "2.0", "method": "exit"}))

    # -- receiving

    def feed(self, data: bytes) -> None:
        for message in self.decoder.feed(data):
            self.handle(message)

    def handle(self, message: dict) -> None:
        method = message.get("method")
        if method and "id" in message:  # a request from the server
            self._write(encode({"jsonrpc": "2.0", "id": message["id"],
                                "result": self._answer(method, message.get("params") or {})}))
        elif method == "textDocument/publishDiagnostics":
            params = message.get("params") or {}
            self.on_diagnostics(params.get("uri", ""), params.get("diagnostics") or [])
        elif method == "window/logMessage" or method == "window/showMessage":
            self.log((message.get("params") or {}).get("message", ""))
        elif "id" in message:
            callback = self.pending.pop(message["id"], None)
            if "error" in message:
                self.log(f"error: {message['error'].get('message', '')}")
                if callback:
                    callback(None)
            elif callback:
                callback(message.get("result"))

    def _answer(self, method: str, params: dict):
        if method == "workspace/configuration":
            return [self.settings if item.get("section") in (None, "", "nixd") else None
                    for item in params.get("items", [])]
        return None


class GioTransport:
    """Runs the server (`argv`) and connects it to `client`; `on_exit()` when it ends."""

    def __init__(self, argv: list[str], make_client: Callable[[Callable], Client],
                 on_exit: Callable[[], None] = lambda: None):
        from gi.repository import Gio, GLib

        self.GLib = GLib
        self.on_exit = on_exit
        # nixd's own log (stderr) is verbose; the editor logs what matters.
        flags = (Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE
                 | Gio.SubprocessFlags.STDERR_SILENCE)
        self.proc = Gio.Subprocess.new(argv, flags)
        self.stdin = self.proc.get_stdin_pipe()
        self.stdout = self.proc.get_stdout_pipe()
        self.client = make_client(self.write)
        self.alive = True
        self._read()
        self.proc.wait_async(None, self._exited)

    def write(self, data: bytes) -> None:
        if not self.alive:
            return
        try:
            self.stdin.write_all(data, None)
            self.stdin.flush(None)
        except self.GLib.Error as e:
            self.client.log(f"cannot write to the server: {e.message}")
            self.alive = False

    def _read(self) -> None:
        self.stdout.read_bytes_async(65536, self.GLib.PRIORITY_DEFAULT, None, self._got)

    def _got(self, stream, result) -> None:
        try:
            data = stream.read_bytes_finish(result).get_data()
        except self.GLib.Error:
            data = b""
        if not data:
            return
        self.client.feed(bytes(data))
        self._read()

    def _exited(self, proc, result) -> None:
        try:
            proc.wait_finish(result)
        except self.GLib.Error:
            pass
        self.alive = False
        self.on_exit()

    def stop(self) -> None:
        if self.alive:
            self.client.shutdown()
            self.proc.force_exit()
