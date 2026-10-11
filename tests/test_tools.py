"""Mock PowerDNS and grocery-list tools, including a stdio MCP adapter."""

from __future__ import annotations

import unittest

from runbyus.common.harness import open_harness
from runbyus.common.tools.mcp_client import call_tool, list_tools


class TestMockTools(unittest.TestCase):
    def test_pdns_query_is_flaky_then_readable(self) -> None:
        with open_harness() as harness:
            first = harness.pdns.dns_query("vlan30.home.example")
            self.assertEqual(first["status"], "SERVFAIL")
            record = harness.pdns.pdns_get_record("vlan30.home.example")
            self.assertTrue(record["flaky"])
            self.assertEqual(record["content"], "10.0.0.1")
            second = harness.pdns.dns_query("vlan30.home.example")
            self.assertEqual(second["status"], "NOERROR")

    def test_pdns_update_is_idempotent(self) -> None:
        with open_harness() as harness:
            key = "wi_test:apply"
            first = harness.pdns.pdns_update_record(
                name="vlan30.home.example",
                content="10.0.0.9",
                idempotency_key=key,
            )
            second = harness.pdns.pdns_update_record(
                name="vlan30.home.example",
                content="10.0.0.9",
                idempotency_key=key,
            )
            self.assertEqual(first["applied"], True)
            self.assertEqual(second["applied"], False)
            self.assertEqual(harness.pdns.update_count("vlan30.home.example"), 1)
            self.assertFalse(harness.pdns.pdns_get_record("vlan30.home.example")["flaky"])

    def test_list_add_item_is_reversible_and_idempotent(self) -> None:
        with open_harness() as harness:
            first = harness.grocery.list_add_item("milk", idempotency_key="wi_a:1")
            second = harness.grocery.list_add_item("milk", idempotency_key="wi_a:1")
            self.assertEqual(first["added"], True)
            self.assertEqual(second["added"], False)
            self.assertEqual(harness.grocery.list_get_items()["items"], ["milk"])

    def test_mcp_stdio_lists_and_calls_pdns_tools(self) -> None:
        with open_harness() as harness:
            names = {tool["name"] for tool in list_tools(harness.pdns_mcp)}
            self.assertEqual(names, {"dns_query", "pdns_get_record", "pdns_update_record"})
            record = call_tool(harness.pdns_mcp, "pdns_get_record", {"name": "vlan30.home.example"})
            self.assertEqual(record["name"], "vlan30.home.example")
            self.assertIn("flaky", record)

    def test_mcp_stdio_lists_and_calls_list_tools(self) -> None:
        with open_harness() as harness:
            names = {tool["name"] for tool in list_tools(harness.list_mcp)}
            self.assertEqual(names, {"list_add_item", "list_get_items"})
            call_tool(
                harness.list_mcp,
                "list_add_item",
                {"item": "eggs", "idempotency_key": "wi_b:1"},
            )
            items = call_tool(harness.list_mcp, "list_get_items", {})
            self.assertEqual(items["items"], ["eggs"])


if __name__ == "__main__":
    unittest.main()
