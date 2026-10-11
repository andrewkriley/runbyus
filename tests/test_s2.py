"""S2: Telegram 'add milk' — rules route, child list agent, reversible write."""

from __future__ import annotations

import unittest

from runbyus.common.harness import open_harness
from runbyus.langgraph.s2 import run as langgraph_s2
from runbyus.pydanticai.s2 import run as pydanticai_s2

RUNTIMES = (
    ("langgraph", langgraph_s2),
    ("pydanticai", pydanticai_s2),
)


class TestS2(unittest.TestCase):
    def test_s2_rules_child_and_notification(self) -> None:
        for name, run in RUNTIMES:
            with self.subTest(runtime=name):
                with open_harness(runtime=name) as harness:
                    parent = run(harness)
                    self.assertEqual(parent.state, "done")
                    self.assertEqual(parent.space_id, harness.policy.space_id("family"))
                    route = harness.ledger.list_routes(parent.id)[0]
                    self.assertEqual(route.tier, "rules")
                    children = harness.ledger.list_children(parent.id)
                    self.assertEqual(len(children), 1)
                    child = children[0]
                    self.assertEqual(child.state, "done")
                    self.assertEqual(child.agent, "list")
                    self.assertEqual(child.parent_id, parent.id)
                    self.assertEqual(harness.grocery.list_get_items()["items"], ["milk"])
                    notes = [
                        msg
                        for msg in harness.ledger.list_messages(parent.thread_id)
                        if msg.author_kind == "agent"
                    ]
                    self.assertTrue(notes)
                    traces = harness.emitter.traces()
                    self.assertEqual(len(traces), 2)
                    child_trace = next(
                        trace for trace in traces if trace["work_item_id"] == child.id
                    )
                    self.assertEqual(child_trace["metadata"]["parent_work_item_id"], parent.id)
                    tools = [
                        span["name"]
                        for span in harness.emitter.spans()
                        if span["kind"] == "tool"
                    ]
                    self.assertIn("list_add_item", tools)


if __name__ == "__main__":
    unittest.main()
