"""Approval records plus a CLI first-answer gate."""

from __future__ import annotations

import argparse
import json
from typing import Any

from runbyus.common.ledger import Ledger
from runbyus.common.models import Approval


class Approvals:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def request(self, work_item_id: str, tool: str, args: dict[str, Any], risk_tier: str) -> Approval:
        item = self.ledger.get_work_item(work_item_id)
        if item.state == "pending":
            self.ledger.set_state(work_item_id, "running")
        approval = self.ledger.add_approval(work_item_id, tool, args, risk_tier)
        if item.state != "awaiting_approval":
            current = self.ledger.get_work_item(work_item_id)
            if current.state == "running":
                self.ledger.set_state(work_item_id, "awaiting_approval")
        return approval

    def decide(self, work_item_id: str, decision: str, decided_by: str, channel: str) -> Approval:
        approval = self.ledger.decide_approval(work_item_id, decision, decided_by, channel)
        item = self.ledger.get_work_item(work_item_id)
        if approval.decision == "denied" and item.state == "awaiting_approval":
            self.ledger.set_state(work_item_id, "cancelled")
        return approval

    def get_for_work_item(self, work_item_id: str) -> Approval:
        approval = self.ledger.get_open_approval(work_item_id)
        if approval is None:
            raise KeyError(work_item_id)
        return approval


def approve_from_cli(db_url: str, work_item_id: str, decision: str, decided_by: str) -> Approval:
    ledger = Ledger.connect(db_url)
    try:
        approvals = Approvals(ledger)
        return approvals.decide(work_item_id, decision, decided_by, "cli")
    finally:
        ledger.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approve or deny a runbyus work item")
    parser.add_argument("decision", choices=("approved", "denied"))
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--db", required=True, help="sqlite:/// path to the ledger")
    parser.add_argument("--by", default="prn_01")
    args = parser.parse_args(argv)
    approval = approve_from_cli(args.db, args.work_item, args.decision, args.by)
    print(json.dumps({"id": approval.id, "decision": approval.decision}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
