"""Emitter maps ledger activity to AO-shaped spans with label redaction."""

from __future__ import annotations

import unittest

from runbyus.common.harness import open_harness


class TestEmitter(unittest.TestCase):
    def test_router_span_carries_work_item_ids(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            route = harness.router.route(item, "powerdns on VLAN 30 is flaky")
            spans = [span for span in harness.emitter.spans() if span["kind"] == "router"]
            self.assertEqual(len(spans), 1)
            self.assertEqual(spans[0]["metadata"]["work_item_id"], item.id)
            self.assertEqual(spans[0]["metadata"]["route_id"], route.id)
            self.assertEqual(spans[0]["session_id"], item.thread_id)

    def test_family_content_is_hashed(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_telegram("add milk")
            harness.emitter.message(item, "add milk", channel="telegram")
            spans = [span for span in harness.emitter.spans() if span["kind"] == "message"]
            self.assertEqual(len(spans), 1)
            self.assertNotIn("add milk", spans[0]["content"])
            self.assertTrue(spans[0]["content"].startswith("sha256:"))

    def test_infra_content_is_kept(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            harness.emitter.message(item, "powerdns on VLAN 30 is flaky", channel="web")
            spans = [span for span in harness.emitter.spans() if span["kind"] == "message"]
            self.assertEqual(spans[0]["content"], "powerdns on VLAN 30 is flaky")

    def test_spans_persist_on_the_ledger(self) -> None:
        with self._tmp_db() as path:
            db_url = f"sqlite:///{path}"
            with open_harness(db_url=db_url) as harness:
                item = harness.ingest_web("powerdns on VLAN 30 is flaky")
                harness.emitter.work_item_started(item)
                harness.emitter.message(item, "powerdns on VLAN 30 is flaky", channel="web")
                thread_id = item.thread_id
            with open_harness(db_url=db_url) as harness:
                traces = harness.ledger.list_ao_traces(thread_id)
                spans = harness.ledger.list_ao_spans(thread_id)
                self.assertTrue(traces)
                self.assertTrue(any(span["kind"] == "message" for span in spans))
                self.assertEqual(spans[0]["session_id"], thread_id)

    def test_queued_child_is_a_new_trace_with_parent_metadata(self) -> None:
        with open_harness() as harness:
            parent = harness.ingest_telegram("add milk")
            child = harness.ledger.create_child_work_item(
                parent, agent="list", trigger_kind="human", trigger_source="delegate"
            )
            harness.emitter.work_item_started(parent)
            harness.emitter.work_item_started(child)
            traces = harness.emitter.traces()
            self.assertEqual(len(traces), 2)
            child_trace = next(trace for trace in traces if trace["work_item_id"] == child.id)
            self.assertEqual(child_trace["session_id"], parent.thread_id)
            self.assertEqual(child_trace["metadata"]["parent_work_item_id"], parent.id)

    def _tmp_db(self):
        from pathlib import Path
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
