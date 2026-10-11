"""Ledger record dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Thread:
    id: str
    space_id: str
    label_id: str
    principal_id: str
    title: str
    enabled_channels: list[str]
    created_at: str


@dataclass
class Message:
    id: str
    thread_id: str
    author_kind: str
    author_id: str
    origin_channel: str
    content: str
    created_at: str


@dataclass
class WorkItem:
    id: str
    parent_id: str | None
    root_id: str
    thread_id: str | None
    space_id: str
    label_id: str
    principal_id: str
    trigger_kind: str
    trigger_source: str
    agent: str
    state: str
    route_id: str | None
    attempt: int
    created_at: str
    updated_at: str


@dataclass
class Route:
    id: str
    work_item_id: str
    tier: str
    provider: str
    model: str
    risk: str
    confidence: float | None
    reason: str
    created_at: str


@dataclass
class Approval:
    id: str
    work_item_id: str
    tool: str
    args_hash: str
    args_json: str
    risk_tier: str
    requested_at: str
    decided_by: str | None = None
    decision: str | None = None
    decided_channel: str | None = None
    decided_at: str | None = None


@dataclass
class Event:
    id: str
    subject_kind: str
    subject_id: str
    type: str
    payload_json: str
    created_at: str


@dataclass
class Classification:
    space: str
    label: str
    intent: str
    complexity: str
    risk: str
    needs_tools: bool
    confidence: float
    extra: dict[str, Any] = field(default_factory=dict)
