"""Agent runtime sits behind this interface (SPEC §8)."""

from __future__ import annotations

import os
from typing import Protocol

from runbyus.common.models import Approval, WorkItem

DEFAULT_RUNTIME = "pydanticai"
RUNTIMES = ("pydanticai", "langgraph")


def want_live(explicit: bool = False) -> bool:
    if explicit:
        return True
    flag = (os.environ.get("RUNBYUS_LIVE") or "").strip().lower()
    return flag in {"1", "true", "yes"}


def resolve_runtime(explicit: str = "") -> str:
    name = (explicit or os.environ.get("RUNBYUS_RUNTIME") or DEFAULT_RUNTIME).strip()
    if name not in RUNTIMES:
        raise ValueError(f"unknown runtime {name}")
    return name


class AgentRuntime(Protocol):
    def start(self, work_item: WorkItem) -> None: ...
    def resume(self, work_item_id: str, approval: Approval) -> WorkItem: ...
    def cancel(self, work_item_id: str) -> None: ...
