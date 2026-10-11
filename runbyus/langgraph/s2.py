"""S2 on LangGraph: Telegram add milk."""

from __future__ import annotations

from runbyus.common.models import WorkItem


def run(harness, text: str | None = None) -> WorkItem:
    harness.use_runtime("langgraph")
    item = harness.ingest_telegram(text or "add milk")
    harness.runtime.start(item)
    return harness.ledger.get_work_item(item.id)
