"""Shared live S1 model loop. Runtimes still own pause/resume."""

from __future__ import annotations

import json

from runbyus.common.llm import (
    READ_TOOLS,
    UPDATE_TOOL,
    merge_update_args,
    openai_assistant_with_tools,
    openai_tool_result,
)
from runbyus.common.models import WorkItem
from runbyus.common.tools.mock_pdns.store import TOOLS


def live_s1_reads(harness, item: WorkItem, text: str) -> list[dict]:
    read_tools = [tool for tool in TOOLS if tool["name"] in READ_TOOLS]
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"{text}\n"
                "Use dns_query and pdns_get_record on vlan30.home.example. "
                "Do not change records."
            ),
        }
    ]
    for _ in range(4):
        result = harness.llm.complete("local", messages, read_tools)
        if not result.tool_calls:
            if result.text:
                messages.append({"role": "assistant", "content": result.text})
            break
        executed: list[tuple] = []
        for index, call in enumerate(result.tool_calls):
            if call.name not in READ_TOOLS:
                continue
            args = dict(call.arguments or {})
            args.setdefault("name", "vlan30.home.example")
            out = harness.call_tool(item, "pdns", call.name, args)
            executed.append((index, call, out))
        if not executed:
            if result.text:
                messages.append({"role": "assistant", "content": result.text})
            break
        messages.append(openai_assistant_with_tools(result, allowed=READ_TOOLS))
        for index, call, out in executed:
            messages.append(openai_tool_result(call, json.dumps(out), index))
    return messages


def _cloud_role(harness) -> str:
    cfg = getattr(harness.llm, "config", None)
    cloud = getattr(cfg, "cloud", "anthropic") if cfg is not None else "anthropic"
    return cloud or "anthropic"


def live_s1_diagnose(harness, item: WorkItem, text: str) -> tuple[str, dict]:
    cloud = _cloud_role(harness)
    harness.router.switch_model(
        item,
        provider=cloud,
        model="cloud-diagnose",
        reason="diagnose after local reads",
    )
    update_tools = [tool for tool in TOOLS if tool["name"] == UPDATE_TOOL]
    record = harness.pdns.pdns_get_record("vlan30.home.example")
    result = harness.llm.complete(
        cloud,
        [
            {
                "role": "user",
                "content": (
                    f"{text}\nCurrent PowerDNS record: {record}\n"
                    "If the record is flaky, call pdns_update_record "
                    "with a stable A record. Do not invent other names."
                ),
            }
        ],
        update_tools,
    )
    incoming = result.tool_calls[0].arguments if result.tool_calls else None
    return result.text, merge_update_args(item.id, incoming)
