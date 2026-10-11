"""Product ingest: channel is the door, router picks space, one ledger."""

from __future__ import annotations

from typing import Any

from runbyus.common.models import WorkItem
from runbyus.common.runtime import resolve_runtime

CHANNELS = ("web", "telegram")


def ingest(
    harness,
    channel: str,
    text: str,
    thread_id: str = "",
    new: bool = False,
) -> WorkItem:
    channel = (channel or "").strip().lower()
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel}")
    body = (text or "").strip()
    if not body:
        raise ValueError("text required")
    harness.use_runtime(resolve_runtime())
    planned = harness.router.plan(body)
    item = harness.ingest_turn(
        body,
        channel=channel,
        space=planned.space,
        label=planned.label,
        agent=planned.agent,
        thread_id=thread_id,
        new=new,
    )
    harness.runtime.start(item)
    item = harness.ledger.get_work_item(item.id)
    harness.ledger.append_event(
        "work_item",
        item.id,
        "operator.run",
        {
            "scenario": "product",
            "runtime": harness.runtime_name,
            "live": bool(getattr(harness.llm, "live", False)),
            "channel": channel,
            "space": planned.space,
            "provider": planned.provider,
            "model": planned.model,
        },
    )
    harness.ledger.append_event(
        "work_item",
        item.id,
        "product.ingest",
        {"channel": channel, "runtime": harness.runtime_name, "space": planned.space},
    )
    return harness.ledger.get_work_item(item.id)


def item_row(harness, item: WorkItem, db_url: str = "") -> dict[str, Any]:
    from runbyus.common.operator import item_view

    view = item_view(harness, item, db_url=db_url)
    view["origin_channel"] = item.trigger_source
    view["space"] = harness.policy.space_name(item.space_id)
    view["runtime"] = view.get("runtime") or harness.runtime_name
    routes = view.get("routes") or []
    if routes:
        view["provider"] = routes[-1].get("provider") or ""
        view["model"] = routes[-1].get("model") or ""
    return view


def feed(harness, db_url: str = "") -> list[dict[str, Any]]:
    rows = []
    for item in harness.ledger.list_work_items():
        if item.parent_id:
            continue
        rows.append(item_row(harness, item, db_url=db_url))
    return rows


def _empty_conversation(channel: str, thread_id: str = "") -> dict[str, Any]:
    return {"channel": channel, "thread_id": thread_id, "chat": [], "latest": None}


def _conversation_from_thread(harness, thread, channel: str, db_url: str = "") -> dict[str, Any]:
    items = [
        item
        for item in harness.ledger.list_work_items()
        if item.thread_id == thread.id and not item.parent_id
    ]
    pending = next((item for item in items if item.state == "awaiting_approval"), None)
    latest = pending or (items[0] if items else None)
    if latest is None:
        from runbyus.common.operator import chat_turns

        messages = [
            {
                "author_kind": message.author_kind,
                "content": message.content,
                "origin_channel": message.origin_channel,
            }
            for message in harness.ledger.list_messages(thread.id)
        ]
        return {
            "channel": channel,
            "thread_id": thread.id,
            "title": thread.title,
            "chat": chat_turns(messages, None),
            "latest": None,
        }
    row = item_row(harness, latest, db_url=db_url)
    row["title"] = thread.title
    return {
        "channel": channel,
        "thread_id": thread.id,
        "title": thread.title,
        "chat": row.get("chat") or [],
        "latest": row,
    }


def conversation(
    harness,
    channel: str = "web",
    thread_id: str = "",
    db_url: str = "",
) -> dict[str, Any]:
    channel = (channel or "web").strip().lower()
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel}")
    chosen = (thread_id or "").strip()
    if chosen:
        return _conversation_from_thread(harness, harness.ledger.get_thread(chosen), channel, db_url)
    if channel == "telegram":
        thread = harness.ledger.find_thread_by_title("product:telegram")
        if thread is None:
            return _empty_conversation(channel)
        return _conversation_from_thread(harness, thread, channel, db_url)
    rows = list_threads(harness, channel=channel)
    if not rows:
        return _empty_conversation(channel)
    return _conversation_from_thread(harness, harness.ledger.get_thread(rows[0]["thread_id"]), channel, db_url)


def list_threads(harness, channel: str = "web") -> list[dict[str, Any]]:
    channel = (channel or "web").strip().lower()
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel}")
    rows: list[dict[str, Any]] = []
    for thread in harness.ledger.list_threads():
        if channel not in thread.enabled_channels:
            continue
        if channel == "web" and "telegram" in thread.enabled_channels:
            continue
        if channel == "telegram" and "telegram" not in thread.enabled_channels:
            continue
        messages = harness.ledger.list_messages(thread.id)
        items = [
            item
            for item in harness.ledger.list_work_items()
            if item.thread_id == thread.id and not item.parent_id
        ]
        pending = next((item for item in items if item.state == "awaiting_approval"), None)
        latest = pending or (items[0] if items else None)
        preview = messages[-1].content[:80] if messages else ""
        updated = latest.updated_at if latest else (messages[-1].created_at if messages else thread.created_at)
        rows.append(
            {
                "thread_id": thread.id,
                "title": thread.title or "New chat",
                "preview": preview,
                "state": latest.state if latest else "",
                "updated_at": updated,
                "channel": channel,
            }
        )
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows


def start_thread(harness, channel: str = "web") -> dict[str, Any]:
    channel = (channel or "web").strip().lower()
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel}")
    thread = harness.start_product_thread(channel)
    return {
        "channel": channel,
        "thread_id": thread.id,
        "title": thread.title,
        "chat": [],
        "latest": None,
    }


def session(harness, thread_id: str) -> dict[str, Any]:
    chosen = (thread_id or "").strip()
    if not chosen:
        raise ValueError("thread_id required")
    thread = harness.ledger.get_thread(chosen)
    return {
        "session_id": thread.id,
        "thread_id": thread.id,
        "title": thread.title,
        "traces": harness.ledger.list_ao_traces(thread.id),
        "spans": harness.ledger.list_ao_spans(thread.id),
    }
