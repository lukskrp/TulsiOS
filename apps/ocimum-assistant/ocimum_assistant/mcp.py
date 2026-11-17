"""Minimal synchronous MCP client for a stdio server (tulsi-mcp).

Calls block: a tools/call may wait for the human's approval and a system
rebuild, so the agent runs it on a worker thread.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import threading
from dataclasses import dataclass

PROTOCOL_VERSION = "2025-06-18"
DEFAULT_COMMAND = "tulsi-mcp"


class McpError(Exception):
    pass


@dataclass
class ToolResult:
    text: str
    is_error: bool
    structured: dict | None = None


class McpClient:
    def __init__(self, command: str | list[str] = DEFAULT_COMMAND):
        self.argv = shlex.split(command) if isinstance(command, str) else list(command)
        self.proc: subprocess.Popen | None = None
        self.instructions = ""
        self.server_name = ""
        self._next_id = 1
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            self.proc = subprocess.Popen(
                self.argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            raise McpError(f"cannot start {self.argv[0]}: {e}") from e
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            # No elicitation: approval happens in tulsi-mcp's desktop dialog.
            "capabilities": {},
            "clientInfo": {"name": "ocimum-assistant", "version": "0.1.0"},
        })
        self.instructions = result.get("instructions", "")
        self.server_name = result.get("serverInfo", {}).get("name", "")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def list_tools(self) -> list[dict]:
        return self._request("tools/list", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> ToolResult:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        structured = result.get("structuredContent")
        return ToolResult("\n".join(texts), bool(result.get("isError")),
                          structured if isinstance(structured, dict) else None)

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
        self.proc = None

    def _send(self, msg: dict) -> None:
        if not self.proc or self.proc.poll() is not None:
            raise McpError("the tulsi-mcp server is not running")
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        except OSError as e:
            raise McpError(f"lost connection to tulsi-mcp: {e}") from e

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise McpError("tulsi-mcp exited unexpectedly")
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "method" in msg:
                    if "id" in msg:  # a server request we do not support
                        self._send({"jsonrpc": "2.0", "id": msg["id"],
                                    "error": {"code": -32601, "message": "not supported"}})
                    continue
                if msg.get("id") != req_id:
                    continue
                if "error" in msg:
                    raise McpError(msg["error"].get("message", "MCP error"))
                return msg.get("result", {})
