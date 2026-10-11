"""Router: static rules first, then the local classifier, then a recorded switch."""

from __future__ import annotations

import unittest

from runbyus.common.harness import open_harness
from runbyus.common.router import Classification, default_classifier


class TestRouter(unittest.TestCase):
    def test_hello_classifies_as_p1_chat(self) -> None:
        result = default_classifier("hello there")
        self.assertEqual(result.space, "p1")
        self.assertEqual(result.label, "personal")
        self.assertEqual(result.intent, "chat")
        self.assertFalse(result.needs_tools)
        self.assertGreaterEqual(result.confidence, 0.7)

    def test_plan_picks_space_before_a_work_item(self) -> None:
        with open_harness() as harness:
            hello = harness.router.plan("hello")
            self.assertEqual(hello.space, "p1")
            self.assertEqual(hello.label, "personal")
            self.assertEqual(hello.agent, "assistant")
            milk = harness.router.plan("add milk")
            self.assertEqual(milk.space, "family")
            self.assertEqual(milk.agent, "list")
            dns = harness.router.plan("powerdns on VLAN 30 is flaky")
            self.assertEqual(dns.space, "infra")
            self.assertEqual(dns.agent, "infra")

    def test_add_milk_is_rules_tier_with_no_model(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_telegram("add milk")
            route = harness.router.route(item, "add milk")
            self.assertEqual(route.tier, "rules")
            self.assertEqual(route.risk, "reversible")
            self.assertEqual(route.provider, "none")
            self.assertEqual(route.model, "")
            stored = harness.ledger.get_route(route.id)
            self.assertEqual(stored.work_item_id, item.id)
            self.assertEqual(item.space_id, harness.policy.space_id("family"))
            self.assertEqual(item.label_id, harness.policy.label_id("shared"))

    def test_powerdns_uses_classifier_when_no_rule_matches(self) -> None:
        classifier = lambda text: Classification(
            space="infra",
            label="infra",
            intent="diagnose_dns",
            complexity="medium",
            risk="impactful",
            needs_tools=True,
            confidence=0.86,
        )
        with open_harness(classifier=classifier) as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            route = harness.router.route(item, "powerdns on VLAN 30 is flaky")
            self.assertEqual(route.tier, "classifier")
            self.assertEqual(route.risk, "impactful")
            self.assertGreaterEqual(route.confidence, 0.7)
            self.assertEqual(route.provider, "local")
            self.assertTrue(route.model)
            spans = harness.emitter.spans()
            self.assertTrue(any(span["kind"] == "router" for span in spans))

    def test_mid_run_switch_writes_a_second_route(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_web("powerdns on VLAN 30 is flaky")
            first = harness.router.route(item, "powerdns on VLAN 30 is flaky")
            second = harness.router.switch_model(
                item,
                provider="anthropic",
                model="cloud-diagnose",
                reason="diagnose after local reads",
            )
            self.assertNotEqual(first.id, second.id)
            routes = harness.ledger.list_routes(item.id)
            self.assertEqual(len(routes), 2)
            self.assertEqual(routes[-1].provider, "anthropic")
            self.assertEqual(routes[-1].tier, "escalated")

    def test_switch_rejected_when_model_not_allowlisted(self) -> None:
        with open_harness() as harness:
            item = harness.ingest_telegram("add milk")
            harness.router.route(item, "add milk")
            with self.assertRaises(PermissionError):
                harness.router.switch_model(
                    item,
                    provider="openai",
                    model="gpt-not-allowed",
                    reason="should fail",
                )


if __name__ == "__main__":
    unittest.main()
