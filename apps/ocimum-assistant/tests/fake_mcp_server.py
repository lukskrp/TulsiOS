"""A tiny stand-in MCP server for the client tests (stdio, JSON lines)."""

import json
import sys

for line in sys.stdin:
    msg = json.loads(line)
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "fake"},
                  "capabilities": {"tools": {}}, "instructions": "be careful"}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "echo", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        # Ask the client something first (it must refuse and keep going).
        print(json.dumps({"jsonrpc": "2.0", "id": "srv-1", "method": "elicitation/create", "params": {}}), flush=True)
        reply = json.loads(sys.stdin.readline())
        assert reply["id"] == "srv-1" and "error" in reply
        args = msg["params"]["arguments"]
        if args.get("fail"):
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "bad args"}}), flush=True)
            continue
        result = {"content": [{"type": "text", "text": json.dumps(args)}], "isError": bool(args.get("tool_error"))}
        if args.get("receipt"):
            result["structuredContent"] = {"receipt": args["receipt"]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "nope"}}), flush=True)
        continue
    print("noise that is not json", flush=True)
    print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)
