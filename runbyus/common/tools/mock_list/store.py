"""In-process / shared-file fake shared grocery list."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class ListStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS item (name TEXT PRIMARY KEY, created_at TEXT NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS idem (key TEXT PRIMARY KEY, result_json TEXT NOT NULL)"
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def list_add_item(self, item: str, idempotency_key: str, list_name: str = "shared") -> dict:
        existing = self.conn.execute("SELECT result_json FROM idem WHERE key = ?", (idempotency_key,)).fetchone()
        if existing:
            cached = json.loads(existing["result_json"])
            cached["added"] = False
            cached["replay"] = True
            return cached
        row = self.conn.execute("SELECT name FROM item WHERE name = ?", (item,)).fetchone()
        if row:
            result = {"added": False, "item": item, "list": list_name}
        else:
            self.conn.execute(
                "INSERT INTO item(name, created_at) VALUES (?, datetime('now'))",
                (item,),
            )
            result = {"added": True, "item": item, "list": list_name}
        self.conn.execute(
            "INSERT INTO idem(key, result_json) VALUES (?,?)",
            (idempotency_key, json.dumps(result)),
        )
        self.conn.commit()
        return result

    def list_get_items(self) -> dict:
        rows = self.conn.execute("SELECT name FROM item ORDER BY created_at").fetchall()
        return {"items": [row["name"] for row in rows]}

    def dispatch(self, name: str, arguments: dict) -> dict:
        if name == "list_add_item":
            return self.list_add_item(
                arguments["item"],
                arguments["idempotency_key"],
                arguments.get("list_name", "shared"),
            )
        if name == "list_get_items":
            return self.list_get_items()
        raise KeyError(name)


TOOLS = [
    {
        "name": "list_add_item",
        "description": "Add an item to the shared grocery list. Reversible.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "list_name": {"type": "string"},
            },
            "required": ["item", "idempotency_key"],
        },
        "risk_tier": "reversible",
    },
    {
        "name": "list_get_items",
        "description": "Read the shared grocery list.",
        "inputSchema": {"type": "object", "properties": {}},
        "risk_tier": "read",
    },
]
