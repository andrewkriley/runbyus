"""Small MCP stdio client used by both runtime adapters."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from runbyus.common.tools.mcp_stdio import read_message, write_message


class McpSession:
    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=merged,
        )
        assert self.proc.stdin and self.proc.stdout
        self._next_id = 1
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "runbyus", "version": "0.1.2"},
            },
        )
        write_message(self.proc.stdin, {"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        assert self.proc.stdin and self.proc.stdout
        msg_id = self._next_id
        self._next_id += 1
        write_message(
            self.proc.stdin,
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}},
        )
        reply = read_message(self.proc.stdout)
        if reply is None:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"MCP server closed: {err}")
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply.get("result")

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._rpc("tools/list")["tools"])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = result["content"][0]["text"]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream and not stream.closed:
                try:
                    stream.close()
                except Exception:
                    pass


def module_command(module: str) -> list[str]:
    return [sys.executable, "-m", module]


def list_tools(session: McpSession) -> list[dict[str, Any]]:
    return session.list_tools()


def call_tool(session: McpSession, name: str, arguments: dict[str, Any]) -> Any:
    return session.call_tool(name, arguments)


def workdir_from_db_url(db_url: str, fallback: Path) -> Path:
    if db_url.endswith(":memory:"):
        return fallback
    path = Path(db_url.replace("sqlite:///", "", 1))
    return path.parent
