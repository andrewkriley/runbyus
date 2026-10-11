"""Impactful writes pause; the CLI is the first-answer gate."""

from __future__ import annotations

import unittest
from pathlib import Path

from runbyus.common.approvals import approve_from_cli
from runbyus.common.harness import open_harness


class TestApprovals(unittest.TestCase):
    def test_request_moves_work_item_to_awaiting_approval(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            harness.ledger.set_state(item.id, "running")
            approval = harness.approvals.request(
                work_item_id=item.id,
                tool="pdns_update_record",
                args={"name": "vlan30.home.example", "content": "10.0.0.9"},
                risk_tier="impactful",
            )
            self.assertEqual(harness.ledger.get_work_item(item.id).state, "awaiting_approval")
            self.assertEqual(approval.decision, None)
            self.assertEqual(approval.risk_tier, "impactful")

    def test_cli_approve_is_first_answer(self) -> None:
        with self._file_harness() as (harness, db_url):
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            harness.ledger.set_state(item.id, "running")
            approval = harness.approvals.request(
                work_item_id=item.id,
                tool="pdns_update_record",
                args={"name": "vlan30.home.example"},
                risk_tier="impactful",
            )
            result = approve_from_cli(db_url, item.id, "approved", decided_by="prn_01")
            self.assertEqual(result.decision, "approved")
            self.assertEqual(result.id, approval.id)
            again = approve_from_cli(db_url, item.id, "denied", decided_by="prn_01")
            self.assertEqual(again.decision, "approved")
            self.assertEqual(again.id, approval.id)

    def test_deny_cancels_work_item(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            harness.ledger.set_state(item.id, "running")
            harness.approvals.request(
                work_item_id=item.id,
                tool="pdns_update_record",
                args={"name": "vlan30.home.example"},
                risk_tier="impactful",
            )
            harness.approvals.decide(item.id, "denied", decided_by="prn_01", channel="cli")
            self.assertEqual(harness.ledger.get_work_item(item.id).state, "cancelled")

    def _file_harness(self):
        from tempfile import TemporaryDirectory

        from runbyus.common.harness import open_harness as _open

        class _Ctx:
            def __enter__(self_inner):
                self_inner.td = TemporaryDirectory()
                path = Path(self_inner.td.name) / "ledger.sqlite"
                self_inner.db_url = f"sqlite:///{path}"
                self_inner.harness = _open(db_url=self_inner.db_url).__enter__()
                return self_inner.harness, self_inner.db_url

            def __exit__(self_inner, *exc):
                self_inner.harness.close()
                self_inner.td.cleanup()

        return _Ctx()


if __name__ == "__main__":
    unittest.main()
