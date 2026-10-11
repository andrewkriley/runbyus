"""Ledger -> Splunk AO shaped spans. Memory backend for tests; SDK later."""

from __future__ import annotations

import hashlib
from typing import Any

from runbyus.common.models import Route, WorkItem
from runbyus.common.policy import Policy

REDACT_LABELS = {"personal", "professional", "shared"}


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class MemoryEmitter:
    """In-memory AO stand-in. One exporter — never pair with a framework callback."""

    def __init__(self, policy: Policy, ledger=None):
        self.policy = policy
        self.ledger = ledger
        self._spans: list[dict[str, Any]] = []
        self._traces: list[dict[str, Any]] = []

    def spans(self) -> list[dict[str, Any]]:
        return list(self._spans)

    def traces(self) -> list[dict[str, Any]]:
        return list(self._traces)

    def router(self, work_item: WorkItem, route: Route) -> None:
        self._store_span(
            {
                "kind": "router",
                "session_id": work_item.thread_id,
                "content": route.reason,
                "metadata": {
                    "work_item_id": work_item.id,
                    "parent_id": work_item.parent_id,
                    "root_id": work_item.root_id,
                    "route_id": route.id,
                    "provider": route.provider,
                    "model": route.model,
                    "reason": route.reason,
                },
            }
        )

    def tool(self, work_item: WorkItem, name: str, args: dict[str, Any], result: Any) -> None:
        self._store_span(
            {
                "kind": "tool",
                "name": name,
                "session_id": work_item.thread_id,
                "content": self._maybe_redact(work_item, str(result)),
                "metadata": {
                    "work_item_id": work_item.id,
                    "parent_id": work_item.parent_id,
                    "root_id": work_item.root_id,
                    "tool": name,
                    "args": args,
                },
            }
        )

    def message(self, work_item: WorkItem, content: str, channel: str) -> None:
        self._store_span(
            {
                "kind": "message",
                "session_id": work_item.thread_id,
                "content": self._maybe_redact(work_item, content),
                "metadata": {
                    "work_item_id": work_item.id,
                    "channel": channel,
                    "principal_id": work_item.principal_id,
                },
            }
        )

    def work_item_started(self, work_item: WorkItem) -> None:
        trace = {
            "work_item_id": work_item.id,
            "session_id": work_item.thread_id or work_item.root_id,
            "metadata": {
                "work_item_id": work_item.id,
                "parent_id": work_item.parent_id,
                "parent_work_item_id": work_item.parent_id,
                "root_id": work_item.root_id,
                "agent": work_item.agent,
            },
        }
        self._traces.append(trace)
        if self.ledger is not None:
            stored = self.ledger.add_ao_trace(trace)
            trace["id"] = stored["id"]
            trace["created_at"] = stored["created_at"]

    def _store_span(self, span: dict[str, Any]) -> None:
        self._spans.append(span)
        if self.ledger is not None:
            stored = self.ledger.add_ao_span(span)
            span["id"] = stored["id"]
            span["created_at"] = stored["created_at"]

    def _maybe_redact(self, work_item: WorkItem, content: str) -> str:
        label = self.policy.label_name(work_item.label_id)
        if label in REDACT_LABELS:
            return _hash(content)
        return content
