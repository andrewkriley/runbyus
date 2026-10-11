"""Product ingest: channel is the door, router picks space. No live network."""

from __future__ import annotations

import unittest

from runbyus.common.harness import open_harness
from runbyus.common.product import conversation, feed, ingest, list_threads, session, start_thread
from runbyus.common.runtime import DEFAULT_RUNTIME


class TestProductIngest(unittest.TestCase):
    def test_web_hello_is_p1_chat_not_infra(self) -> None:
        with open_harness() as harness:
            item = ingest(harness, channel="web", text="hello")
            self.assertEqual(harness.runtime_name, DEFAULT_RUNTIME)
            self.assertEqual(DEFAULT_RUNTIME, "pydanticai")
            self.assertEqual(item.trigger_source, "web")
            self.assertEqual(item.space_id, harness.policy.space_id("p1"))
            self.assertEqual(item.state, "done")
            notes = [
                msg
                for msg in harness.ledger.list_messages(item.thread_id)
                if msg.author_kind == "agent"
            ]
            self.assertTrue(notes)
            self.assertIn("infra", notes[0].content.lower())

    def test_web_dns_is_infra_on_default_pydantic(self) -> None:
        with open_harness() as harness:
            item = ingest(harness, channel="web", text="powerdns on VLAN 30 is flaky")
            self.assertEqual(item.trigger_source, "web")
            self.assertEqual(item.space_id, harness.policy.space_id("infra"))
            self.assertEqual(item.state, "awaiting_approval")
            messages = harness.ledger.list_messages(item.thread_id)
            self.assertEqual(messages[0].origin_channel, "web")
            self.assertEqual(messages[0].content, "powerdns on VLAN 30 is flaky")

    def test_web_add_milk_is_family(self) -> None:
        with open_harness() as harness:
            item = ingest(harness, channel="web", text="add milk")
            self.assertEqual(item.trigger_source, "web")
            self.assertEqual(item.space_id, harness.policy.space_id("family"))
            self.assertEqual(item.state, "done")
            self.assertEqual(harness.grocery.list_get_items()["items"], ["milk"])

    def test_telegram_dns_is_infra_on_same_ledger(self) -> None:
        with open_harness() as harness:
            hello = ingest(harness, channel="web", text="hello")
            tg = ingest(harness, channel="telegram", text="powerdns on VLAN 30 is flaky")
            self.assertEqual(tg.trigger_source, "telegram")
            self.assertEqual(tg.space_id, harness.policy.space_id("infra"))
            self.assertEqual(tg.state, "awaiting_approval")
            self.assertEqual(hello.space_id, harness.policy.space_id("p1"))
            ids = {item.id for item in harness.ledger.list_work_items()}
            self.assertIn(hello.id, ids)
            self.assertIn(tg.id, ids)

    def test_telegram_add_milk_is_family_on_same_ledger(self) -> None:
        with open_harness() as harness:
            web = ingest(harness, channel="web", text="powerdns on VLAN 30 is flaky")
            tg = ingest(harness, channel="telegram", text="add milk")
            self.assertEqual(tg.trigger_source, "telegram")
            self.assertEqual(tg.space_id, harness.policy.space_id("family"))
            self.assertEqual(tg.state, "done")
            self.assertEqual(web.space_id, harness.policy.space_id("infra"))
            self.assertEqual(harness.grocery.list_get_items()["items"], ["milk"])
            notes = [
                msg
                for msg in harness.ledger.list_messages(tg.thread_id)
                if msg.author_kind == "agent"
            ]
            self.assertTrue(notes)
            self.assertEqual(notes[0].origin_channel, "telegram")

    def test_second_web_turn_reuses_the_product_thread(self) -> None:
        with open_harness() as harness:
            first = ingest(harness, channel="web", text="hello")
            second = ingest(harness, channel="web", text="powerdns on VLAN 30 is flaky")
            self.assertEqual(first.thread_id, second.thread_id)
            self.assertNotEqual(first.id, second.id)
            contents = [msg.content for msg in harness.ledger.list_messages(first.thread_id)]
            self.assertIn("hello", contents)
            self.assertIn("powerdns on VLAN 30 is flaky", contents)

    def test_conversation_is_one_thread_per_channel(self) -> None:
        with open_harness() as harness:
            ingest(harness, channel="web", text="hello")
            ingest(harness, channel="web", text="add milk")
            ingest(harness, channel="telegram", text="hello")
            web = conversation(harness, channel="web")
            tg = conversation(harness, channel="telegram")
            self.assertEqual(web["channel"], "web")
            self.assertEqual(tg["channel"], "telegram")
            self.assertNotEqual(web["thread_id"], tg["thread_id"])
            human = [turn["content"] for turn in web["chat"] if turn["role"] == "human"]
            self.assertEqual(human, ["hello", "add milk"])
            self.assertEqual(web["latest"]["space"], "family")
            self.assertTrue(any(turn.get("role") == "assistant" for turn in web["chat"]))

    def test_feed_lists_both_channels_in_realtime(self) -> None:
        with open_harness() as harness:
            ingest(harness, channel="web", text="powerdns on VLAN 30 is flaky")
            ingest(harness, channel="telegram", text="add milk")
            rows = feed(harness)
            channels = {row["origin_channel"] for row in rows}
            spaces = {row["space"] for row in rows}
            self.assertEqual(channels, {"web", "telegram"})
            self.assertEqual(spaces, {"infra", "family"})
            self.assertTrue(all(row["runtime"] == "pydanticai" for row in rows))
            self.assertTrue(any(row["state"] == "awaiting_approval" for row in rows))
            self.assertTrue(any(row["state"] == "done" for row in rows))

    def test_new_web_chat_mints_a_thread(self) -> None:
        with open_harness() as harness:
            first = ingest(harness, channel="web", text="hello")
            second = ingest(harness, channel="web", text="add milk", new=True)
            self.assertNotEqual(first.thread_id, second.thread_id)
            rows = list_threads(harness, channel="web")
            ids = {row["thread_id"] for row in rows}
            self.assertEqual(ids, {first.thread_id, second.thread_id})
            titles = {row["title"] for row in rows}
            self.assertIn("hello", titles)
            self.assertIn("add milk", titles)

    def test_pickup_continues_named_thread(self) -> None:
        with open_harness() as harness:
            first = ingest(harness, channel="web", text="hello")
            other = ingest(harness, channel="web", text="add milk", new=True)
            pickup = ingest(
                harness,
                channel="web",
                text="powerdns on VLAN 30 is flaky",
                thread_id=first.thread_id,
            )
            self.assertEqual(pickup.thread_id, first.thread_id)
            self.assertNotEqual(pickup.thread_id, other.thread_id)
            convo = conversation(harness, thread_id=first.thread_id)
            self.assertEqual(convo["thread_id"], first.thread_id)
            human = [turn["content"] for turn in convo["chat"] if turn["role"] == "human"]
            self.assertEqual(human, ["hello", "powerdns on VLAN 30 is flaky"])
            empty = start_thread(harness, channel="web")
            self.assertEqual(empty["title"], "New chat")
            self.assertNotEqual(empty["thread_id"], first.thread_id)
            listed = list_threads(harness, channel="web")
            self.assertTrue(any(row["thread_id"] == empty["thread_id"] for row in listed))

    def test_session_lists_traces_and_redacts_family(self) -> None:
        with open_harness() as harness:
            hello = ingest(harness, channel="web", text="hello")
            milk = ingest(harness, channel="web", text="add milk", new=True)
            hello_session = session(harness, hello.thread_id)
            self.assertEqual(hello_session["session_id"], hello.thread_id)
            self.assertTrue(hello_session["traces"])
            self.assertTrue(hello_session["spans"])
            kinds = {span["kind"] for span in hello_session["spans"]}
            self.assertIn("router", kinds)
            self.assertIn("message", kinds)
            milk_session = session(harness, milk.thread_id)
            contents = " ".join(str(span.get("content") or "") for span in milk_session["spans"])
            self.assertNotIn("milk", contents.lower())
            self.assertTrue(any(str(span.get("content") or "").startswith("sha256:") for span in milk_session["spans"]))

    def test_unknown_channel_is_rejected(self) -> None:
        with open_harness() as harness:
            with self.assertRaises(ValueError):
                ingest(harness, channel="slack", text="hello")


if __name__ == "__main__":
    unittest.main()
