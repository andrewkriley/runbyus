"""In-process / shared-file fake PowerDNS with a flaky VLAN 30 record."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class PdnsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS record (
                name TEXT PRIMARY KEY,
                rtype TEXT NOT NULL,
                content TEXT NOT NULL,
                flaky INTEGER NOT NULL,
                fails_left INTEGER NOT NULL,
                updates INTEGER NOT NULL DEFAULT 0
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS idem (
                key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL
            )"""
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO record(name, rtype, content, flaky, fails_left, updates) VALUES (?,?,?,?,?,?)",
            ("vlan30.home.example", "A", "10.0.0.1", 1, 1, 0),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def dns_query(self, name: str) -> dict:
        row = self._get(name)
        if row is None:
            return {"name": name, "status": "NXDOMAIN"}
        if row["fails_left"] > 0:
            self.conn.execute(
                "UPDATE record SET fails_left = fails_left - 1 WHERE name = ?",
                (name,),
            )
            self.conn.commit()
            return {"name": name, "status": "SERVFAIL", "reason": "flaky vlan 30"}
        return {"name": name, "status": "NOERROR", "type": row["rtype"], "content": row["content"]}

    def pdns_get_record(self, name: str) -> dict:
        row = self._get(name)
        if row is None:
            return {"name": name, "found": False}
        return {
            "name": name,
            "found": True,
            "type": row["rtype"],
            "content": row["content"],
            "flaky": bool(row["flaky"]),
        }

    def pdns_update_record(self, name: str, content: str, idempotency_key: str) -> dict:
        existing = self.conn.execute("SELECT result_json FROM idem WHERE key = ?", (idempotency_key,)).fetchone()
        if existing:
            cached = json.loads(existing["result_json"])
            cached["applied"] = False
            cached["replay"] = True
            return cached
        row = self._get(name)
        if row is None:
            result = {"applied": False, "error": "not found"}
        else:
            self.conn.execute(
                "UPDATE record SET content = ?, flaky = 0, fails_left = 0, updates = updates + 1 WHERE name = ?",
                (content, name),
            )
            result = {"applied": True, "name": name, "content": content}
        self.conn.execute(
            "INSERT INTO idem(key, result_json) VALUES (?,?)",
            (idempotency_key, json.dumps(result)),
        )
        self.conn.commit()
        return result

    def update_count(self, name: str) -> int:
        row = self._get(name)
        return int(row["updates"]) if row else 0

    def _get(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM record WHERE name = ?", (name,)).fetchone()

    def dispatch(self, name: str, arguments: dict) -> dict:
        if name == "dns_query":
            return self.dns_query(arguments["name"])
        if name == "pdns_get_record":
            return self.pdns_get_record(arguments["name"])
        if name == "pdns_update_record":
            return self.pdns_update_record(
                arguments["name"],
                arguments["content"],
                arguments["idempotency_key"],
            )
        raise KeyError(name)


TOOLS = [
    {
        "name": "dns_query",
        "description": "Resolver query against the fake PowerDNS. VLAN 30 is flaky.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "risk_tier": "read",
    },
    {
        "name": "pdns_get_record",
        "description": "Read one PowerDNS record, including the flaky flag.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "risk_tier": "read",
    },
    {
        "name": "pdns_update_record",
        "description": "Change a record. Impactful. Requires idempotency_key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "content": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["name", "content", "idempotency_key"],
        },
        "risk_tier": "impactful",
    },
]
