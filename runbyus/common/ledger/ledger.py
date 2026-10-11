"""Append-only work ledger. SQLite for tests; same schema on Postgres."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from runbyus.common.ids import new_id
from runbyus.common.models import (
    Approval,
    Event,
    Message,
    Route,
    Thread,
    WorkItem,
)
from runbyus.common.policy import load_policy

SCHEMA = Path(__file__).with_name("schema.sql")

TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"awaiting_approval", "done", "failed"},
    "awaiting_approval": {"running", "cancelled"},
    "failed": {"pending"},
    "done": set(),
    "cancelled": set(),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_sqlite_url(url: str) -> str:
    if url == "sqlite:///:memory:":
        return ":memory:"
    parsed = urlparse(url)
    if parsed.scheme != "sqlite":
        raise ValueError(f"unsupported ledger url: {url}")
    path = unquote(parsed.path)
    if path.startswith("/") and len(path) > 1 and path[2] == ":":
        path = path[1:]
    return path


class Ledger:
    def __init__(self, conn: sqlite3.Connection, url: str):
        self.conn = conn
        self.url = url
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()

    def _execute(self, sql: str, params: tuple = ()):
        with self._lock:
            return self.conn.execute(sql, params)

    def _executescript(self, sql: str) -> None:
        with self._lock:
            self.conn.executescript(sql)

    def _commit(self) -> None:
        with self._lock:
            self.conn.commit()

    @classmethod
    def connect(cls, url: str) -> "Ledger":
        path = _parse_sqlite_url(url)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return cls(conn, url)

    def apply_schema(self) -> None:
        self._executescript(SCHEMA.read_text(encoding="utf-8"))
        self._commit()

    def seed_policy(self) -> None:
        policy = load_policy()
        created = now()
        for row in policy.raw["principals"]:
            self.conn.execute(
                "INSERT OR IGNORE INTO principal(id, name, active, created_at) VALUES (?,?,?,?)",
                (row["id"], row["name"], 1 if row.get("active", True) else 0, created),
            )
        for row in policy.raw["labels"]:
            self.conn.execute(
                "INSERT OR IGNORE INTO label(id, name) VALUES (?,?)",
                (row["id"], row["name"]),
            )
        for row in policy.raw["spaces"]:
            self.conn.execute(
                "INSERT OR IGNORE INTO space(id, name, created_at) VALUES (?,?,?)",
                (row["id"], row["name"], created),
            )
            for label_id in row.get("labels", []):
                self.conn.execute(
                    "INSERT OR IGNORE INTO space_label(space_id, label_id) VALUES (?,?)",
                    (row["id"], label_id),
                )
            for principal_id in row.get("members", []):
                self.conn.execute(
                    "INSERT OR IGNORE INTO membership(space_id, principal_id, role, since) VALUES (?,?,?,?)",
                    (row["id"], principal_id, "member", created),
                )
        for row in policy.raw.get("channel_accounts", []):
            self.conn.execute(
                "INSERT OR IGNORE INTO channel_account(id, principal_id, channel, external_user_id) VALUES (?,?,?,?)",
                (row["id"], row["principal_id"], row["channel"], row["external_user_id"]),
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def append_event(
        self,
        subject_kind: str,
        subject_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            id=new_id("evt"),
            subject_kind=subject_kind,
            subject_id=subject_id,
            type=event_type,
            payload_json=json.dumps(payload or {}),
            created_at=now(),
        )
        with self._lock:
            self.conn.execute(
                "INSERT INTO event(id, subject_kind, subject_id, type, payload_json, created_at) VALUES (?,?,?,?,?,?)",
                (
                    event.id,
                    event.subject_kind,
                    event.subject_id,
                    event.type,
                    event.payload_json,
                    event.created_at,
                ),
            )
            self.conn.commit()
        return event

    def list_events(self, subject_id: str | None = None) -> list[Event]:
        if subject_id:
            rows = self.conn.execute(
                "SELECT * FROM event WHERE subject_id = ? ORDER BY created_at",
                (subject_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM event ORDER BY created_at").fetchall()
        return [Event(**dict(row)) for row in rows]

    def create_thread(
        self,
        space_id: str,
        label_id: str,
        principal_id: str,
        title: str,
        enabled_channels: list[str],
    ) -> Thread:
        thread = Thread(
            id=new_id("thr"),
            space_id=space_id,
            label_id=label_id,
            principal_id=principal_id,
            title=title,
            enabled_channels=list(enabled_channels),
            created_at=now(),
        )
        self.conn.execute(
            "INSERT INTO thread(id, space_id, label_id, principal_id, title, enabled_channels, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                thread.id,
                thread.space_id,
                thread.label_id,
                thread.principal_id,
                thread.title,
                json.dumps(thread.enabled_channels),
                thread.created_at,
            ),
        )
        self.conn.commit()
        self.append_event("thread", thread.id, "thread.created", {"title": title})
        return thread

    def list_threads(self) -> list[Thread]:
        rows = self.conn.execute("SELECT * FROM thread ORDER BY created_at").fetchall()
        threads = []
        for row in rows:
            data = dict(row)
            data["enabled_channels"] = json.loads(data["enabled_channels"])
            threads.append(Thread(**data))
        return threads

    def find_thread_by_title(self, title: str) -> Thread | None:
        for thread in self.list_threads():
            if thread.title == title:
                return thread
        return None

    def get_thread(self, thread_id: str) -> Thread:
        row = self.conn.execute("SELECT * FROM thread WHERE id = ?", (thread_id,)).fetchone()
        if row is None:
            raise KeyError(thread_id)
        data = dict(row)
        data["enabled_channels"] = json.loads(data["enabled_channels"])
        return Thread(**data)

    def add_message(
        self,
        thread_id: str,
        author_kind: str,
        author_id: str,
        origin_channel: str,
        content: str,
    ) -> Message:
        message = Message(
            id=new_id("msg"),
            thread_id=thread_id,
            author_kind=author_kind,
            author_id=author_id,
            origin_channel=origin_channel,
            content=content,
            created_at=now(),
        )
        self.conn.execute(
            "INSERT INTO message(id, thread_id, author_kind, author_id, origin_channel, content, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                message.id,
                message.thread_id,
                message.author_kind,
                message.author_id,
                message.origin_channel,
                message.content,
                message.created_at,
            ),
        )
        self.conn.commit()
        self.append_event("message", message.id, "message.created", {"thread_id": thread_id})
        return message

    def list_messages(self, thread_id: str) -> list[Message]:
        rows = self.conn.execute(
            "SELECT * FROM message WHERE thread_id = ? ORDER BY created_at",
            (thread_id,),
        ).fetchall()
        return [Message(**dict(row)) for row in rows]

    def create_work_item(
        self,
        thread_id: str | None,
        space_id: str,
        label_id: str,
        principal_id: str,
        trigger_kind: str,
        trigger_source: str,
        agent: str,
        parent_id: str | None = None,
        root_id: str | None = None,
    ) -> WorkItem:
        created = now()
        item_id = new_id("wi")
        item = WorkItem(
            id=item_id,
            parent_id=parent_id,
            root_id=root_id or item_id,
            thread_id=thread_id,
            space_id=space_id,
            label_id=label_id,
            principal_id=principal_id,
            trigger_kind=trigger_kind,
            trigger_source=trigger_source,
            agent=agent,
            state="pending",
            route_id=None,
            attempt=0,
            created_at=created,
            updated_at=created,
        )
        self.conn.execute(
            """INSERT INTO work_item(
                id, parent_id, root_id, thread_id, space_id, label_id, principal_id,
                trigger_kind, trigger_source, agent, state, route_id, attempt, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item.id,
                item.parent_id,
                item.root_id,
                item.thread_id,
                item.space_id,
                item.label_id,
                item.principal_id,
                item.trigger_kind,
                item.trigger_source,
                item.agent,
                item.state,
                item.route_id,
                item.attempt,
                item.created_at,
                item.updated_at,
            ),
        )
        self.conn.commit()
        self.append_event("work_item", item.id, "work_item.created", {"agent": agent})
        return item

    def create_child_work_item(
        self,
        parent: WorkItem,
        agent: str,
        trigger_kind: str,
        trigger_source: str,
    ) -> WorkItem:
        return self.create_work_item(
            thread_id=parent.thread_id,
            space_id=parent.space_id,
            label_id=parent.label_id,
            principal_id=parent.principal_id,
            trigger_kind=trigger_kind,
            trigger_source=trigger_source,
            agent=agent,
            parent_id=parent.id,
            root_id=parent.root_id,
        )

    def get_work_item(self, work_item_id: str) -> WorkItem:
        row = self.conn.execute("SELECT * FROM work_item WHERE id = ?", (work_item_id,)).fetchone()
        if row is None:
            raise KeyError(work_item_id)
        return WorkItem(**dict(row))

    def list_work_items(self) -> list[WorkItem]:
        rows = self.conn.execute("SELECT * FROM work_item ORDER BY created_at DESC").fetchall()
        return [WorkItem(**dict(row)) for row in rows]

    def list_children(self, parent_id: str) -> list[WorkItem]:
        rows = self.conn.execute(
            "SELECT * FROM work_item WHERE parent_id = ? ORDER BY created_at",
            (parent_id,),
        ).fetchall()
        return [WorkItem(**dict(row)) for row in rows]

    def set_state(self, work_item_id: str, state: str) -> WorkItem:
        item = self.get_work_item(work_item_id)
        allowed = TRANSITIONS.get(item.state, set())
        if state not in allowed:
            raise ValueError(f"cannot move {item.state} -> {state}")
        updated = now()
        self.conn.execute(
            "UPDATE work_item SET state = ?, updated_at = ? WHERE id = ?",
            (state, updated, work_item_id),
        )
        self.conn.commit()
        self.append_event("work_item", work_item_id, f"work_item.state.{state}", {})
        return self.get_work_item(work_item_id)

    def set_route_id(self, work_item_id: str, route_id: str) -> None:
        self.conn.execute(
            "UPDATE work_item SET route_id = ?, updated_at = ? WHERE id = ?",
            (route_id, now(), work_item_id),
        )
        self.conn.commit()

    def add_route(
        self,
        work_item_id: str,
        tier: str,
        provider: str,
        model: str,
        risk: str,
        confidence: float | None,
        reason: str,
    ) -> Route:
        route = Route(
            id=new_id("rte"),
            work_item_id=work_item_id,
            tier=tier,
            provider=provider,
            model=model,
            risk=risk,
            confidence=confidence,
            reason=reason,
            created_at=now(),
        )
        self.conn.execute(
            "INSERT INTO route(id, work_item_id, tier, provider, model, risk, confidence, reason, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                route.id,
                route.work_item_id,
                route.tier,
                route.provider,
                route.model,
                route.risk,
                route.confidence,
                route.reason,
                route.created_at,
            ),
        )
        self.conn.commit()
        self.set_route_id(work_item_id, route.id)
        self.append_event("route", route.id, "route.created", {"tier": tier, "provider": provider})
        return route

    def get_route(self, route_id: str) -> Route:
        row = self.conn.execute("SELECT * FROM route WHERE id = ?", (route_id,)).fetchone()
        if row is None:
            raise KeyError(route_id)
        return Route(**dict(row))

    def list_routes(self, work_item_id: str) -> list[Route]:
        rows = self.conn.execute(
            "SELECT * FROM route WHERE work_item_id = ? ORDER BY created_at",
            (work_item_id,),
        ).fetchall()
        return [Route(**dict(row)) for row in rows]

    def add_approval(
        self,
        work_item_id: str,
        tool: str,
        args: dict[str, Any],
        risk_tier: str,
    ) -> Approval:
        args_json = json.dumps(args, sort_keys=True)
        approval = Approval(
            id=new_id("apr"),
            work_item_id=work_item_id,
            tool=tool,
            args_hash=str(abs(hash(args_json))),
            args_json=args_json,
            risk_tier=risk_tier,
            requested_at=now(),
        )
        self.conn.execute(
            """INSERT INTO approval(
                id, work_item_id, tool, args_hash, args_json, risk_tier, requested_at,
                decided_by, decision, decided_channel, decided_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                approval.id,
                approval.work_item_id,
                approval.tool,
                approval.args_hash,
                approval.args_json,
                approval.risk_tier,
                approval.requested_at,
                None,
                None,
                None,
                None,
            ),
        )
        self.conn.commit()
        self.append_event("approval", approval.id, "approval.requested", {"tool": tool})
        return approval

    def get_approval(self, approval_id: str) -> Approval:
        row = self.conn.execute("SELECT * FROM approval WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return Approval(**dict(row))

    def get_open_approval(self, work_item_id: str) -> Approval | None:
        row = self.conn.execute(
            "SELECT * FROM approval WHERE work_item_id = ? ORDER BY requested_at DESC LIMIT 1",
            (work_item_id,),
        ).fetchone()
        return Approval(**dict(row)) if row else None

    def decide_approval(
        self,
        work_item_id: str,
        decision: str,
        decided_by: str,
        channel: str,
    ) -> Approval:
        current = self.get_open_approval(work_item_id)
        if current is None:
            raise KeyError(work_item_id)
        if current.decision:
            return current
        decided_at = now()
        self.conn.execute(
            "UPDATE approval SET decision = ?, decided_by = ?, decided_channel = ?, decided_at = ? WHERE id = ?",
            (decision, decided_by, channel, decided_at, current.id),
        )
        self.conn.commit()
        self.append_event("approval", current.id, f"approval.{decision}", {"channel": channel})
        return self.get_approval(current.id)

    def put_runtime_state(self, work_item_id: str, kind: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO runtime_state(work_item_id, kind, payload_json, updated_at)
               VALUES (?,?,?,?)
               ON CONFLICT(work_item_id) DO UPDATE SET kind=excluded.kind, payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
            (work_item_id, kind, json.dumps(payload), now()),
        )
        self.conn.commit()

    def get_runtime_state(self, work_item_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload_json FROM runtime_state WHERE work_item_id = ?",
            (work_item_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def set_thread_title(self, thread_id: str, title: str) -> Thread:
        self.get_thread(thread_id)
        self.conn.execute(
            "UPDATE thread SET title = ? WHERE id = ?",
            (title, thread_id),
        )
        self.conn.commit()
        self.append_event("thread", thread_id, "thread.retitled", {"title": title})
        return self.get_thread(thread_id)

    def add_ao_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        row = {
            "id": trace.get("id") or new_id("trc"),
            "work_item_id": trace["work_item_id"],
            "session_id": trace["session_id"],
            "metadata": dict(trace.get("metadata") or {}),
            "created_at": trace.get("created_at") or now(),
        }
        with self._lock:
            self.conn.execute(
                "INSERT INTO ao_trace(id, work_item_id, session_id, metadata_json, created_at) VALUES (?,?,?,?,?)",
                (row["id"], row["work_item_id"], row["session_id"], json.dumps(row["metadata"]), row["created_at"]),
            )
            self.conn.commit()
        return row

    def add_ao_span(self, span: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(span.get("metadata") or {})
        row = {
            "id": span.get("id") or new_id("spn"),
            "kind": span["kind"],
            "name": span.get("name") or "",
            "session_id": span["session_id"],
            "content": span.get("content") or "",
            "metadata": metadata,
            "created_at": span.get("created_at") or now(),
        }
        work_item_id = metadata.get("work_item_id") or span.get("work_item_id") or ""
        payload = json.dumps(metadata)
        with self._lock:
            self.conn.execute(
                "INSERT INTO ao_span(id, work_item_id, session_id, kind, name, content, metadata_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    row["id"],
                    work_item_id,
                    row["session_id"],
                    row["kind"],
                    row["name"],
                    row["content"],
                    payload,
                    row["created_at"],
                ),
            )
            self.conn.commit()
        return row

    def list_ao_traces(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM ao_trace WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        traces = []
        for row in rows:
            traces.append(
                {
                    "id": row["id"],
                    "work_item_id": row["work_item_id"],
                    "session_id": row["session_id"],
                    "metadata": json.loads(row["metadata_json"]),
                    "created_at": row["created_at"],
                }
            )
        return traces

    def list_ao_spans(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM ao_span WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        spans = []
        for row in rows:
            spans.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "session_id": row["session_id"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata_json"]),
                    "created_at": row["created_at"],
                }
            )
        return spans
