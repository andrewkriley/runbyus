"""Shared operator actions for the CLI and the runbyus web UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from runbyus.common.harness import open_harness
from runbyus.common.llm import LiveConfig, LlmClient, http_json, openai_models_url
from runbyus.common.product import conversation as product_conversation
from runbyus.common.product import feed as product_feed_rows
from runbyus.common.product import ingest as product_ingest_item
from runbyus.common.product import item_row
from runbyus.common.product import list_threads as product_threads
from runbyus.common.product import session as product_session
from runbyus.common.product import start_thread as product_start_thread
from runbyus.common.runtime import RUNTIMES, resolve_runtime, want_live
from runbyus.common.targets import (
    CLOUD_IDS,
    DEFAULT_CLOUD,
    DEFAULT_TARGET,
    LOCAL_TARGETS,
    TARGET_IDS,
)
from runbyus.langgraph.s1 import run as langgraph_s1
from runbyus.langgraph.s2 import run as langgraph_s2
from runbyus.pydanticai.s1 import run as pydanticai_s1
from runbyus.pydanticai.s2 import run as pydanticai_s2

SCENARIOS = {
    ("s1", "langgraph"): langgraph_s1,
    ("s1", "pydanticai"): pydanticai_s1,
    ("s2", "langgraph"): langgraph_s2,
    ("s2", "pydanticai"): pydanticai_s2,
}


class LiveIncomplete(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("live config incomplete: " + ", ".join(missing))


def resolve_db(explicit: str = "") -> str:
    if explicit:
        return explicit
    path = Path(os.environ.get("RUNBYUS_WORKDIR") or (Path.cwd() / ".runbyus")) / "ledger.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def options() -> dict[str, Any]:
    return {
        "runtimes": list(RUNTIMES),
        "scenarios": ["s1", "s2"],
        "targets": list(TARGET_IDS),
        "clouds": list(CLOUD_IDS),
        "defaults": {
            "runtime": resolve_runtime(),
            "target": DEFAULT_TARGET,
            "cloud": DEFAULT_CLOUD,
            "live": False,
        },
    }


def live_llm(required: bool, target: str = DEFAULT_TARGET, cloud: str = DEFAULT_CLOUD):
    cfg = LiveConfig.from_env().with_target(target).with_cloud(cloud)
    if not required:
        return None
    if not cfg.ready:
        raise LiveIncomplete(cfg.missing(target=target, cloud=cloud))
    return LlmClient(cfg)


def doctor() -> dict[str, Any]:
    cfg = LiveConfig.from_env()
    report: dict[str, Any] = {
        "ready": cfg.all_targets_ready(),
        "missing": cfg.missing(),
        "config": cfg.public_dict(),
        "targets": {},
    }
    for spec in LOCAL_TARGETS:
        pick = cfg.targets[spec.id]
        entry: dict[str, Any] = {"ready": cfg.target_ready(spec.id), "model": pick.model}
        if pick.base_url:
            try:
                http_json(
                    openai_models_url(pick.base_url),
                    method="GET",
                    headers=({"authorization": f"Bearer {pick.api_key}"} if pick.api_key else {}),
                    json=None,
                    timeout=5,
                )
                entry["models"] = "ok"
            except Exception as exc:  # noqa: BLE001
                entry["models"] = "error"
                entry["reason"] = type(exc).__name__
        report["targets"][spec.id] = entry
    public = cfg.public_dict()
    report["clouds"] = {
        "anthropic": {
            "ready": cfg.cloud_ready("anthropic"),
            "model": cfg.anthropic_model,
            "api_key": public["anthropic_api_key"],
        },
        "openai": {
            "ready": cfg.cloud_ready("openai"),
            "model": cfg.openai_model,
            "api_key": public["openai_api_key"],
        },
    }
    return report


def ingest_product(
    db_url: str,
    channel: str,
    text: str,
    live: bool = False,
    target: str = DEFAULT_TARGET,
    cloud: str = DEFAULT_CLOUD,
    thread_id: str = "",
    new: bool = False,
) -> dict[str, Any]:
    runtime = resolve_runtime()
    use_live = want_live(live)
    llm = None
    if use_live:
        try:
            llm = live_llm(True, target, cloud)
        except LiveIncomplete:
            llm = None
    with open_harness(db_url=db_url, runtime=runtime, llm=llm) as harness:
        item = product_ingest_item(
            harness,
            channel=channel,
            text=text,
            thread_id=thread_id,
            new=new,
        )
        return item_row(harness, item, db_url=db_url)


def list_product_feed(db_url: str) -> list[dict[str, Any]]:
    with open_harness(db_url=db_url) as harness:
        return product_feed_rows(harness, db_url=db_url)


def list_product_conversation(
    db_url: str,
    channel: str = "web",
    thread_id: str = "",
) -> dict[str, Any]:
    with open_harness(db_url=db_url) as harness:
        return product_conversation(harness, channel=channel, thread_id=thread_id, db_url=db_url)


def list_product_threads(db_url: str, channel: str = "web") -> list[dict[str, Any]]:
    with open_harness(db_url=db_url) as harness:
        return product_threads(harness, channel=channel)


def start_product_thread(db_url: str, channel: str = "web") -> dict[str, Any]:
    with open_harness(db_url=db_url) as harness:
        return product_start_thread(harness, channel=channel)


def list_product_session(db_url: str, thread_id: str) -> dict[str, Any]:
    with open_harness(db_url=db_url) as harness:
        return product_session(harness, thread_id)


def run(
    db_url: str,
    scenario: str,
    runtime: str,
    live: bool = False,
    target: str = DEFAULT_TARGET,
    cloud: str = DEFAULT_CLOUD,
    message: str = "",
) -> dict[str, Any]:
    runtime = resolve_runtime(runtime)
    if (scenario, runtime) not in SCENARIOS:
        raise ValueError(f"unknown scenario/runtime {scenario}/{runtime}")
    llm = live_llm(live, target, cloud)
    runner = SCENARIOS[(scenario, runtime)]
    with open_harness(db_url=db_url, runtime=runtime, llm=llm) as harness:
        item = runner(harness, text=message.strip() or None)
        harness.ledger.append_event(
            "work_item",
            item.id,
            "operator.run",
            {
                "scenario": scenario,
                "runtime": runtime,
                "live": bool(llm),
                "target": target,
                "cloud": cloud,
            },
        )
        return item_view(harness, harness.ledger.get_work_item(item.id), db_url=db_url)


def decide(
    db_url: str,
    work_item_id: str,
    decision: str,
    decided_by: str = "prn_01",
    channel: str = "web",
) -> dict[str, Any]:
    with open_harness(db_url=db_url) as harness:
        approval = harness.approvals.decide(work_item_id, decision, decided_by, channel)
        return {
            "id": approval.id,
            "decision": approval.decision,
            "work_item_id": work_item_id,
        }


def resume(
    db_url: str,
    runtime: str,
    work_item_id: str,
    live: bool = False,
    target: str = DEFAULT_TARGET,
    cloud: str = DEFAULT_CLOUD,
) -> dict[str, Any]:
    runtime = resolve_runtime(runtime)
    llm = live_llm(live, target, cloud)
    with open_harness(db_url=db_url, runtime=runtime, llm=llm) as harness:
        approval = harness.approvals.get_for_work_item(work_item_id)
        item = harness.runtime.resume(work_item_id, approval)
        return item_view(harness, item, db_url=db_url)


def show(db_url: str, work_item_id: str) -> dict[str, Any]:
    with open_harness(db_url=db_url) as harness:
        item = harness.ledger.get_work_item(work_item_id)
        return item_view(harness, item, db_url=db_url)


def list_items(db_url: str) -> list[dict[str, Any]]:
    with open_harness(db_url=db_url) as harness:
        return [item_view(harness, item, db_url=db_url) for item in harness.ledger.list_work_items()]


def chat_turns(
    messages: list[dict[str, Any]],
    approval: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for message in messages:
        turns.append(
            {
                "role": "human" if message.get("author_kind") == "principal" else "assistant",
                "kind": "message",
                "content": message.get("content") or "",
            }
        )
    if approval:
        tool = str(approval.get("tool") or "tool")
        decision = approval.get("decision")
        content = (
            f"{decision}: `{tool}`."
            if decision
            else f"Needs your approval to run `{tool}`."
        )
        turns.append(
            {
                "role": "assistant",
                "kind": "approval",
                "content": content,
                "tool": tool,
                "decision": decision,
                "args": approval.get("args") or {},
            }
        )
    return turns


def item_view(harness, item, db_url: str = "") -> dict[str, Any]:
    run_meta: dict[str, Any] = {}
    for event in harness.ledger.list_events(subject_id=item.id):
        if event.type == "operator.run":
            run_meta = json.loads(event.payload_json)
    approval = harness.ledger.get_open_approval(item.id)
    messages = harness.ledger.list_messages(item.thread_id) if item.thread_id else []
    message_views = [
        {
            "author_kind": message.author_kind,
            "content": message.content,
            "origin_channel": message.origin_channel,
        }
        for message in messages
    ]
    approval_view = (
        {
            "id": approval.id,
            "tool": approval.tool,
            "decision": approval.decision,
            "args": json.loads(approval.args_json) if approval.args_json else {},
        }
        if approval
        else None
    )
    return {
        "work_item_id": item.id,
        "state": item.state,
        "agent": item.agent,
        "parent_id": item.parent_id,
        "thread_id": item.thread_id,
        "scenario": run_meta.get("scenario"),
        "runtime": run_meta.get("runtime"),
        "live": run_meta.get("live"),
        "target": run_meta.get("target"),
        "cloud": run_meta.get("cloud"),
        "db": db_url,
        "routes": [
            {
                "id": route.id,
                "tier": route.tier,
                "provider": route.provider,
                "model": route.model,
                "reason": route.reason,
            }
            for route in harness.ledger.list_routes(item.id)
        ],
        "approval": approval_view,
        "children": [
            {"work_item_id": child.id, "state": child.state, "agent": child.agent}
            for child in harness.ledger.list_children(item.id)
        ],
        "messages": message_views,
        "chat": chat_turns(message_views, approval_view),
        "events": [
            {"type": event.type, "created_at": event.created_at}
            for event in harness.ledger.list_events(subject_id=item.id)
        ],
    }
