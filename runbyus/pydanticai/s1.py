"""S1 on PydanticAI: flaky VLAN 30 PowerDNS."""

from __future__ import annotations

from runbyus.common.models import WorkItem


def run(harness, until: str = "done", text: str | None = None) -> WorkItem:
    harness.use_runtime("pydanticai")
    item = harness.ingest_web(text or "powerdns on VLAN 30 is flaky")
    harness.runtime.start(item)
    return harness.ledger.get_work_item(item.id)
