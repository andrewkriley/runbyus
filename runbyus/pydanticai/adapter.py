"""PydanticAI runtime: Agent + FunctionModel; ledger owns the pause."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import Agent, ModelResponse, RunContext, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from runbyus.common.models import Approval, WorkItem


@dataclass
class ToolDeps:
    harness: object
    work_item: WorkItem


def _local_model(messages: list, info: AgentInfo) -> ModelResponse:
    have_return = any(
        getattr(part, "part_kind", None) == "tool-return"
        for message in messages
        for part in getattr(message, "parts", [])
    )
    if not have_return:
        return ModelResponse(
            parts=[
                ToolCallPart("dns_query", {"name": "vlan30.home.example"}),
                ToolCallPart("pdns_get_record", {"name": "vlan30.home.example"}),
            ]
        )
    return ModelResponse(parts=[TextPart("local reads complete")])


def _cloud_model(messages: list, info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("flaky flag on vlan30.home.example; replace the A record")])


def _build_read_agent() -> Agent:
    agent = Agent(FunctionModel(_local_model), deps_type=ToolDeps, name="infra-local")

    @agent.tool
    def dns_query(ctx: RunContext[ToolDeps], name: str) -> str:
        return json.dumps(ctx.deps.harness.call_tool(ctx.deps.work_item, "pdns", "dns_query", {"name": name}))

    @agent.tool
    def pdns_get_record(ctx: RunContext[ToolDeps], name: str) -> str:
        return json.dumps(
            ctx.deps.harness.call_tool(ctx.deps.work_item, "pdns", "pdns_get_record", {"name": name})
        )

    return agent


def _build_cloud_agent() -> Agent:
    return Agent(FunctionModel(_cloud_model), deps_type=ToolDeps, name="infra-cloud")


class PydanticAIRuntime:
    def __init__(self, harness):
        self.harness = harness
        self._read_agent = _build_read_agent()
        self._cloud_agent = _build_cloud_agent()

    def start(self, work_item: WorkItem) -> None:
        if work_item.state == "pending":
            self.harness.ledger.set_state(work_item.id, "running")
        text = self._text(work_item)
        self.harness.emitter.work_item_started(work_item)
        self.harness.router.route(work_item, text)
        space = self.harness.policy.space_name(work_item.space_id)
        if space == "family":
            self._run_s2(work_item, text)
            return
        if space == "infra":
            self._run_s1_until_approval(work_item, text)
            return
        from runbyus.common.assistant import reply_chat

        reply_chat(self.harness, work_item, text)

    def resume(self, work_item_id: str, approval: Approval) -> WorkItem:
        item = self.harness.ledger.get_work_item(work_item_id)
        if approval.decision != "approved":
            if item.state == "awaiting_approval":
                self.harness.ledger.set_state(work_item_id, "cancelled")
            return self.harness.ledger.get_work_item(work_item_id)
        if item.state == "awaiting_approval":
            self.harness.ledger.set_state(work_item_id, "running")
            item = self.harness.ledger.get_work_item(work_item_id)
        args = json.loads(approval.args_json)
        self.harness.call_tool(item, "pdns", "pdns_update_record", args)
        if item.state == "running":
            self.harness.ledger.set_state(item.id, "done")
        return self.harness.ledger.get_work_item(item.id)

    def cancel(self, work_item_id: str) -> None:
        item = self.harness.ledger.get_work_item(work_item_id)
        if item.state in {"pending", "awaiting_approval"}:
            self.harness.ledger.set_state(work_item_id, "cancelled")

    def _text(self, work_item: WorkItem) -> str:
        if not work_item.thread_id:
            return ""
        messages = self.harness.ledger.list_messages(work_item.thread_id)
        return messages[-1].content if messages else ""

    def _run_s1_until_approval(self, work_item: WorkItem, text: str) -> None:
        if self.harness.llm.live:
            from runbyus.common.live import live_s1_diagnose, live_s1_reads

            live_s1_reads(self.harness, work_item, text)
            diagnosis, args = live_s1_diagnose(self.harness, work_item, text)
            self.harness.approvals.request(work_item.id, "pdns_update_record", args, "impactful")
            self.harness.ledger.put_runtime_state(
                work_item.id,
                "pydanticai",
                {"phase": "awaiting", "diagnosis": diagnosis, "args": args},
            )
            return
        deps = ToolDeps(self.harness, work_item)
        result = asyncio.run(self._read_agent.run(text, deps=deps))
        self.harness.ledger.put_runtime_state(
            work_item.id,
            "pydanticai",
            {"phase": "local", "output": str(result.output)},
        )
        self.harness.router.switch_model(
            work_item,
            provider="anthropic",
            model="cloud-diagnose",
            reason="diagnose after local reads",
        )
        cloud = asyncio.run(self._cloud_agent.run(text, deps=deps))
        args = {
            "name": "vlan30.home.example",
            "content": "10.0.0.9",
            "idempotency_key": f"{work_item.id}:apply",
        }
        self.harness.approvals.request(work_item.id, "pdns_update_record", args, "impactful")
        self.harness.ledger.put_runtime_state(
            work_item.id,
            "pydanticai",
            {"phase": "awaiting", "diagnosis": str(cloud.output), "args": args},
        )

    def _run_s2(self, parent: WorkItem, text: str) -> None:
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
        parent = self.harness.ledger.get_work_item(parent.id)
        if parent.state == "running":
            self.harness.ledger.set_state(parent.id, "done")
