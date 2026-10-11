"""Minimal MCP stdio server (JSON-RPC + Content-Length)."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable


def read_message(stdin) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stdin.readline()
        if line == "":
            return None
        if line in ("\r\n", "\n"):
            break
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = stdin.read(length)
    return json.loads(body)


def write_message(stdout, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    stdout.write(f"Content-Length: {len(data)}\r\n\r\n")
    stdout.write(data.decode("utf-8"))
    stdout.flush()


def serve(tools: list[dict[str, Any]], dispatch: Callable[[str, dict], dict]) -> None:
    stdin = sys.stdin
    stdout = sys.stdout
    while True:
        message = read_message(stdin)
        if message is None:
            return
        method = message.get("method")
        msg_id = message.get("id")
        if method == "initialize":
            write_message(
                stdout,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "runbyus-mock", "version": "0.1.2"},
                    },
                },
            )
            continue
        if method == "notifications/initialized":
            continue
        if method == "tools/list":
            write_message(
                stdout,
                {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}},
            )
            continue
        if method == "tools/call":
            params = message.get("params") or {}
            name = params["name"]
            arguments = params.get("arguments") or {}
            try:
                result = dispatch(name, arguments)
                write_message(
                    stdout,
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result)}]
                        },
                    },
                )
            except Exception as exc:  # noqa: BLE001 — MCP error path
                write_message(
                    stdout,
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32000, "message": str(exc)},
                    },
                )
            continue
        if msg_id is not None:
            write_message(
                stdout,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"unknown method {method}"},
                },
            )
