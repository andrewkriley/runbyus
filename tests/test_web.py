"""Operator web UI drives both stacks. Scripted path only — no live network."""

from __future__ import annotations

import json
import os
import threading
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from runbyus.common.llm import LiveConfig
from runbyus.web import make_server


def _json(url: str, payload: dict | None = None, method: str | None = None) -> tuple[int, dict | list | str]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
        method = method or "POST"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            if resp.headers.get_content_type() == "application/json":
                return resp.status, json.loads(body)
            return resp.status, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed


class TestWeb(unittest.TestCase):
    def test_healthz_is_ok(self) -> None:
        with self._server() as base:
            status, payload = _json(base + "/healthz")
            self.assertEqual(status, 200)
            self.assertEqual(payload, {"ok": True})
            status, payload = _json(base + "/api/health")
            self.assertEqual(status, 200)
            self.assertEqual(payload, {"ok": True})

    def test_home_is_product_assistant(self) -> None:
        with self._server() as base:
            status, html = _json(base + "/")
            self.assertEqual(status, 200)
            self.assertIn("data-product-composer", html)
            self.assertIn("assistant", html.lower())
            self.assertNotIn("Send to both", html)
            self.assertNotIn('data-thread="langgraph"', html)
            status, css = _json(base + "/tokens.css")
            self.assertEqual(status, 200)
            self.assertIn("--bg-canvas", css)
            self.assertIn("--accent-default", css)
            status, js = _json(base + "/app.js")
            self.assertEqual(status, 200)
            self.assertIn("/api/product/ingest", js)

    def test_options_list_both_stacks(self) -> None:
        with self._server() as base:
            status, payload = _json(base + "/api/options")
            self.assertEqual(status, 200)
            self.assertEqual(payload["runtimes"], ["pydanticai", "langgraph"])
            self.assertEqual(payload["defaults"]["runtime"], "pydanticai")
            self.assertIn("s1", payload["scenarios"])
            self.assertIn("local", payload["targets"])
            self.assertIn("openai", payload["clouds"])

    def test_scripted_s1_both_runtimes_approve_and_resume(self) -> None:
        with self._server() as base:
            for runtime in ("langgraph", "pydanticai"):
                with self.subTest(runtime=runtime):
                    status, started = _json(
                        base + "/api/run",
                        {"scenario": "s1", "runtime": runtime},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(started["state"], "awaiting_approval")
                    self.assertEqual(started["runtime"], runtime)
                    self.assertEqual(started["scenario"], "s1")
                    self.assertFalse(started["live"])
                    work_item_id = started["work_item_id"]

                    status, shown = _json(base + f"/api/items/{work_item_id}")
                    self.assertEqual(status, 200)
                    self.assertEqual(shown["approval"]["tool"], "pdns_update_record")
                    self.assertGreaterEqual(len(shown["routes"]), 2)
                    chat = shown["chat"]
                    self.assertTrue(any(turn["role"] == "human" for turn in chat))
                    self.assertTrue(any(turn["kind"] == "approval" for turn in chat))
                    self.assertIn("powerdns on VLAN 30 is flaky", " ".join(turn["content"] for turn in chat))

                    status, decided = _json(
                        base + f"/api/items/{work_item_id}/approve",
                        {},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(decided["decision"], "approved")

                    status, done = _json(
                        base + f"/api/items/{work_item_id}/resume",
                        {"runtime": runtime},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(done["state"], "done")

    def test_scripted_s2_both_runtimes(self) -> None:
        with self._server() as base:
            for runtime in ("langgraph", "pydanticai"):
                with self.subTest(runtime=runtime):
                    status, payload = _json(
                        base + "/api/run",
                        {"scenario": "s2", "runtime": runtime},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(payload["state"], "done")
                    self.assertEqual(payload["scenario"], "s2")
                    self.assertEqual(payload["runtime"], runtime)

    def test_run_uses_human_message_on_both_stacks(self) -> None:
        text = "powerdns on VLAN 30 is flaky from the chat"
        with self._server() as base:
            for runtime in ("langgraph", "pydanticai"):
                with self.subTest(runtime=runtime):
                    status, started = _json(
                        base + "/api/run",
                        {"scenario": "s1", "runtime": runtime, "message": text},
                    )
                    self.assertEqual(status, 200)
                    human = [turn for turn in started["chat"] if turn["role"] == "human"]
                    self.assertTrue(human)
                    self.assertEqual(human[0]["content"], text)
                    self.assertEqual(started["messages"][0]["content"], text)

    def test_list_includes_both_stacks(self) -> None:
        with self._server() as base:
            _json(base + "/api/run", {"scenario": "s2", "runtime": "langgraph"})
            _json(base + "/api/run", {"scenario": "s2", "runtime": "pydanticai"})
            status, items = _json(base + "/api/items")
            self.assertEqual(status, 200)
            runtimes = {item["runtime"] for item in items if item.get("runtime")}
            self.assertEqual(runtimes, {"langgraph", "pydanticai"})

    def test_live_refuses_when_config_incomplete(self) -> None:
        with self._server() as base:
            with patch.object(LiveConfig, "from_env", return_value=LiveConfig.from_env({})):
                status, payload = _json(
                    base + "/api/run",
                    {
                        "scenario": "s1",
                        "runtime": "pydanticai",
                        "live": True,
                        "target": "local",
                        "cloud": "openai",
                    },
                )
            self.assertEqual(status, 400)
            self.assertIn("RUNBYUS_LOCAL_BASE_URL", payload["missing"])
            self.assertIn("RUNBYUS_OPENAI_API_KEY", payload["missing"])

    def test_doctor_hides_secret_values(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("RUNBYUS_")}
        env["RUNBYUS_ANTHROPIC_API_KEY"] = "sk-ant-should-not-print"
        with patch.dict("os.environ", env, clear=True), self._server() as base:
            status, payload = _json(base + "/api/doctor")
        self.assertEqual(status, 200)
        blob = json.dumps(payload)
        self.assertNotIn("sk-ant-should-not-print", blob)
        self.assertIn("RUNBYUS_LOCAL_BASE_URL", blob)

    def _server(self):
        class _Ctx:
            def __enter__(self_inner):
                os.environ["RUNBYUS_UI_QUIET"] = "1"
                self_inner.td = TemporaryDirectory()
                db = f"sqlite:///{self_inner.td.name}/ledger.sqlite"
                self_inner.httpd = make_server(db, host="127.0.0.1", port=0)
                self_inner.thread = threading.Thread(target=self_inner.httpd.serve_forever, daemon=True)
                self_inner.thread.start()
                host, port = self_inner.httpd.server_address
                return f"http://{host}:{port}"

            def __exit__(self_inner, *exc):
                self_inner.httpd.shutdown()
                self_inner.httpd.server_close()
                self_inner.td.cleanup()

        return _Ctx()


if __name__ == "__main__":
    unittest.main()
