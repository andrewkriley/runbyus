"""LangGraph runtime: graph nodes + interrupt() + sqlite checkpointer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from runbyus.common.models import Approval, WorkItem


class GraphState(TypedDict, total=False):
    work_item_id: str
    text: str
    scenario: str
    diagnosis: str
    update_args: dict


class LangGraphRuntime:
    def __init__(self, harness):
        self.harness = harness
        self._checkpointer, self._ckpt_conn = self._open_checkpointer()
        self.graph = self._build().compile(checkpointer=self._checkpointer)

    def _open_checkpointer(self):
        url = self.harness.ledger.url
        if url.endswith(":memory:"):
            return MemorySaver(), None
        path = Path(self.harness.workdir) / "langgraph.ckpt.sqlite"
        conn = sqlite3.connect(str(path), check_same_thread=False)
        return SqliteSaver(conn), conn

    def _build(self):
        graph = StateGraph(GraphState)
        graph.add_node("route", self._route)
        graph.add_node("local_reads", self._local_reads)
        graph.add_node("cloud_diagnose", self._cloud_diagnose)
        graph.add_node("propose", self._propose)
        graph.add_node("apply", self._apply)
        graph.add_node("family_list", self._family_list)
        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            lambda state: state.get("scenario", "s1"),
            {"s1": "local_reads", "s2": "family_list"},
        )
        graph.add_edge("local_reads", "cloud_diagnose")
        graph.add_edge("cloud_diagnose", "propose")
        graph.add_edge("propose", "apply")
        graph.add_edge("apply", END)
        graph.add_edge("family_list", END)
        return graph

    def _config(self, work_item_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": work_item_id}}

    def start(self, work_item: WorkItem) -> None:
        if work_item.state == "pending":
            self.harness.ledger.set_state(work_item.id, "running")
        text = self._text(work_item)
        space = self.harness.policy.space_name(work_item.space_id)
        if space == "family":
            scenario = "s2"
        elif space == "infra":
            scenario = "s1"
        else:
            from runbyus.common.assistant import reply_chat

            reply_chat(self.harness, work_item, text)
            return
        self.graph.invoke(
            {"work_item_id": work_item.id, "text": text, "scenario": scenario},
            self._config(work_item.id),
        )

    def resume(self, work_item_id: str, approval: Approval) -> WorkItem:
        item = self.harness.ledger.get_work_item(work_item_id)
        if approval.decision != "approved":
            if item.state == "awaiting_approval":
                self.harness.ledger.set_state(work_item_id, "cancelled")
            return self.harness.ledger.get_work_item(work_item_id)
        if item.state == "awaiting_approval":
            self.harness.ledger.set_state(work_item_id, "running")
        self.graph.invoke(Command(resume=approval.decision), self._config(work_item_id))
        return self.harness.ledger.get_work_item(work_item_id)

    def cancel(self, work_item_id: str) -> None:
        item = self.harness.ledger.get_work_item(work_item_id)
        if item.state in {"pending", "awaiting_approval"}:
            self.harness.ledger.set_state(work_item_id, "cancelled")

    def _text(self, work_item: WorkItem) -> str:
        if not work_item.thread_id:
            return ""
        messages = self.harness.ledger.list_messages(work_item.thread_id)
        return messages[-1].content if messages else ""

    def _route(self, state: GraphState) -> GraphState:
        item = self.harness.ledger.get_work_item(state["work_item_id"])
        self.harness.emitter.work_item_started(item)
        self.harness.router.route(item, state.get("text", ""))
        return {}

    def _local_reads(self, state: GraphState) -> GraphState:
        item = self.harness.ledger.get_work_item(state["work_item_id"])
        if self.harness.llm.live:
            from runbyus.common.live import live_s1_reads

            live_s1_reads(self.harness, item, state.get("text", ""))
            return {}
        self.harness.call_tool(item, "pdns", "dns_query", {"name": "vlan30.home.example"})
        self.harness.call_tool(item, "pdns", "pdns_get_record", {"name": "vlan30.home.example"})
        return {}

    def _cloud_diagnose(self, state: GraphState) -> GraphState:
        item = self.harness.ledger.get_work_item(state["work_item_id"])
        if self.harness.llm.live:
            from runbyus.common.live import live_s1_diagnose

            diagnosis, args = live_s1_diagnose(self.harness, item, state.get("text", ""))
            return {"diagnosis": diagnosis, "update_args": args}
        self.harness.router.switch_model(
            item,
            provider="anthropic",
            model="cloud-diagnose",
            reason="diagnose after local reads",
        )
        return {"diagnosis": "flaky flag on vlan30.home.example; replace the A record"}

    def _propose(self, state: GraphState) -> GraphState:
        item = self.harness.ledger.get_work_item(state["work_item_id"])
        args = state.get("update_args") or {
            "name": "vlan30.home.example",
            "content": "10.0.0.9",
            "idempotency_key": f"{item.id}:apply",
        }
        existing = self.harness.ledger.get_open_approval(item.id)
        if existing is None or existing.decision is None:
            self.harness.approvals.request(item.id, "pdns_update_record", args, "impactful")
        decision = interrupt({"tool": "pdns_update_record", "args": args})
        return {"diagnosis": state.get("diagnosis", ""), "text": str(decision)}

    def _apply(self, state: GraphState) -> GraphState:
        item = self.harness.ledger.get_work_item(state["work_item_id"])
        approval = self.harness.ledger.get_open_approval(item.id)
        args = json.loads(approval.args_json) if approval else {
            "name": "vlan30.home.example",
            "content": "10.0.0.9",
            "idempotency_key": f"{item.id}:apply",
        }
        self.harness.call_tool(item, "pdns", "pdns_update_record", args)
        if item.state == "running":
            self.harness.ledger.set_state(item.id, "done")
        return {}

    def _family_list(self, state: GraphState) -> GraphState:
        parent = self.harness.ledger.get_work_item(state["work_item_id"])
        child = self.harness.ledger.create_child_work_item(
            parent, agent="list", trigger_kind="human", trigger_source="delegate"
        )
        self.harness.ledger.set_state(child.id, "running")
        self.harness.emitter.work_item_started(child)
        self.harness.call_tool(
            child,
            "list",
            "list_add_item",
            {"item": "milk", "idempotency_key": f"{child.id}:add"},
        )
        self.harness.ledger.add_message(
            parent.thread_id,
            "agent",
            "list",
            parent.trigger_source or "telegram",
            "added milk to the shared list",
        )
        self.harness.ledger.set_state(child.id, "done")
        if parent.state == "running":
            self.harness.ledger.set_state(parent.id, "done")
        return {}
