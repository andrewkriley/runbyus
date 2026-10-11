"""Ledger is the source of truth for threads, work items, routes and events."""

from __future__ import annotations

import unittest
from pathlib import Path

from runbyus.common.harness import open_harness
from runbyus.common.ledger import Ledger


class TestLedger(unittest.TestCase):
    def test_ingest_web_message_creates_pending_work_item(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            self.assertTrue(item.id.startswith("wi_"))
            self.assertEqual(item.state, "pending")
            self.assertEqual(item.trigger_kind, "human")
            self.assertEqual(item.space_id, harness.policy.space_id("infra"))
            thread = harness.ledger.get_thread(item.thread_id)
            self.assertIn("web", thread.enabled_channels)
            messages = harness.ledger.list_messages(item.thread_id)
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].origin_channel, "web")
            events = harness.ledger.list_events(subject_id=item.id)
            self.assertTrue(any(event.type == "work_item.created" for event in events))

    def test_state_changes_are_append_only_events(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            harness.ledger.set_state(item.id, "running")
            harness.ledger.set_state(item.id, "awaiting_approval")
            loaded = harness.ledger.get_work_item(item.id)
            self.assertEqual(loaded.state, "awaiting_approval")
            types = [event.type for event in harness.ledger.list_events(subject_id=item.id)]
            self.assertIn("work_item.state.running", types)
            self.assertIn("work_item.state.awaiting_approval", types)

    def test_invalid_transition_is_rejected(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            with self.assertRaises(ValueError):
                harness.ledger.set_state(item.id, "done")

    def test_child_work_item_keeps_parent_and_root(self) -> None:
        with open_harness() as harness:
            parent = harness.ingest_telegram("add milk")
            child = harness.ledger.create_child_work_item(
                parent,
                agent="list",
                trigger_kind="human",
                trigger_source="delegate",
            )
            self.assertEqual(child.parent_id, parent.id)
            self.assertEqual(child.root_id, parent.id)
            self.assertEqual(child.space_id, parent.space_id)
            self.assertEqual(child.thread_id, parent.thread_id)

    def test_list_work_items_newest_first(self) -> None:
        with open_harness() as harness:
            first = harness.ingest_web("powerdns on VLAN 30 is flaky")
            second = harness.ingest_telegram("add milk")
            ids = [item.id for item in harness.ledger.list_work_items()]
            self.assertEqual(ids[0], second.id)
            self.assertIn(first.id, ids)

    def test_file_ledger_survives_reopen(self) -> None:
        with self._tmp_db() as path:
            first = Ledger.connect(f"sqlite:///{path}")
            first.apply_schema()
            first.seed_policy()
            thread = first.create_thread(
                space_id="spc_01",
                label_id="lbl_03",
                principal_id="prn_01",
                title="vlan 30",
                enabled_channels=["web"],
            )
            item = first.create_work_item(
                thread_id=thread.id,
                space_id="spc_01",
                label_id="lbl_03",
                principal_id="prn_01",
                trigger_kind="human",
                trigger_source="web",
                agent="infra",
            )
            first.set_state(item.id, "running")
            first.close()

            second = Ledger.connect(f"sqlite:///{path}")
            loaded = second.get_work_item(item.id)
            self.assertEqual(loaded.state, "running")
            self.assertEqual(loaded.thread_id, thread.id)
            second.close()

    def _tmp_db(self):
        from tempfile import TemporaryDirectory

        class _Ctx:
            def __enter__(self_inner):
                self_inner.td = TemporaryDirectory()
                return Path(self_inner.td.name) / "ledger.sqlite"

            def __exit__(self_inner, *exc):
                self_inner.td.cleanup()

        return _Ctx()


if __name__ == "__main__":
    unittest.main()
