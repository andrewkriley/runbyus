"""Generic product chat reply. Scripted by default; live uses the local target."""

from __future__ import annotations

SCRIPTED_CHAT = "Okay. I can help with home infra, family lists, and everyday questions."


def reply_chat(harness, work_item, text: str) -> str:
    channel = work_item.trigger_source or "web"
    reply = SCRIPTED_CHAT
    if getattr(harness.llm, "live", False):
        history = []
        if work_item.thread_id:
            for message in harness.ledger.list_messages(work_item.thread_id):
                role = "user" if message.author_kind == "principal" else "assistant"
                history.append({"role": role, "content": message.content})
        if not history:
            history = [{"role": "user", "content": text}]
        try:
            result = harness.llm.complete("local", history, [])
            reply = (result.text or "").strip() or SCRIPTED_CHAT
        except Exception:
            reply = SCRIPTED_CHAT
    if work_item.thread_id:
        harness.ledger.add_message(
            work_item.thread_id,
            "agent",
            "assistant",
            channel,
            reply,
        )
        harness.emitter.message(work_item, reply, channel=channel)
    item = harness.ledger.get_work_item(work_item.id)
    if item.state == "running":
        harness.ledger.set_state(work_item.id, "done")
    return reply
