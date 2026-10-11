"""Product UI is the only chat on /. Bake-off soak is closed. /app redirects."""

from __future__ import annotations

import json
import os
import threading
import unittest
from tempfile import TemporaryDirectory
import urllib.request
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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


def _head(url: str) -> tuple[int, str]:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = Request(url, method="GET")
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, resp.headers.get("location") or ""
    except HTTPError as exc:
        return exc.code, exc.headers.get("Location") or exc.headers.get("location") or ""


class TestProductWeb(unittest.TestCase):
    def test_home_is_assistant_chat_not_bakeoff(self) -> None:
        with self._server() as base:
            status, html = _json(base + "/")
            self.assertEqual(status, 200)
            self.assertIn("data-product-composer", html)
            self.assertIn("data-product-thread", html)
            self.assertIn("data-product-history", html)
            self.assertIn("data-product-inspect", html)
            self.assertIn("data-new-chat", html)
            self.assertIn("assistant", html.lower())
            self.assertIn("router", html.lower())
            self.assertNotIn("Operator soak", html)
            self.assertNotIn("web is infra", html.lower())
            self.assertNotIn("telegram is family", html.lower())
            self.assertNotIn("data-chip", html)
            self.assertNotIn("Send to both", html)
            self.assertNotIn('data-thread="langgraph"', html)
            self.assertNotIn('data-thread="pydanticai"', html)
            status, css = _json(base + "/tokens.css")
            self.assertEqual(status, 200)
            self.assertIn("--bg-canvas", css)
            status, js = _json(base + "/app.js")
            self.assertEqual(status, 200)
            self.assertIn("/api/product/ingest", js)
            self.assertIn("/api/product/conversation", js)
            self.assertIn("/api/product/threads", js)
            self.assertIn("/api/product/session", js)
            self.assertIn("thread_id", js)
            self.assertIn("Thinking", js)
            self.assertNotIn("data-chip", js)
            self.assertNotIn("PROMPTS", js)
            self.assertNotIn("/api/run", js)

    def test_app_path_redirects_home(self) -> None:
        with self._server() as base:
            status, location = _head(base + "/app")
            self.assertEqual(status, 302)
            self.assertTrue(location.endswith("/") or location.endswith(base + "/"))
            status, location = _head(base + "/app/")
            self.assertEqual(status, 302)

    def test_product_ingest_routes_by_text_not_channel(self) -> None:
        with self._server() as base:
            status, hello = _json(
                base + "/api/product/ingest",
                {"channel": "web", "text": "hello"},
            )
            self.assertEqual(status, 200)
            self.assertEqual(hello["origin_channel"], "web")
            self.assertEqual(hello["space"], "p1")
            self.assertEqual(hello["runtime"], "pydanticai")
            self.assertEqual(hello["state"], "done")
            status, milk = _json(
                base + "/api/product/ingest",
                {"channel": "web", "text": "add milk"},
            )
            self.assertEqual(status, 200)
            self.assertEqual(milk["space"], "family")
            self.assertEqual(milk["thread_id"], hello["thread_id"])
            status, tg = _json(
                base + "/api/product/ingest",
                {"channel": "telegram", "text": "powerdns on VLAN 30 is flaky"},
            )
            self.assertEqual(status, 200)
            self.assertEqual(tg["origin_channel"], "telegram")
            self.assertEqual(tg["space"], "infra")
            self.assertEqual(tg["state"], "awaiting_approval")
            status, convo = _json(base + "/api/product/conversation?channel=web")
            self.assertEqual(status, 200)
            self.assertEqual(convo["channel"], "web")
            self.assertEqual(convo["thread_id"], hello["thread_id"])
            human = [turn["content"] for turn in convo["chat"] if turn["role"] == "human"]
            self.assertEqual(human, ["hello", "add milk"])

    def test_product_approve_and_resume_web_item(self) -> None:
        with self._server() as base:
            _, started = _json(
                base + "/api/product/ingest",
                {"channel": "web", "text": "powerdns on VLAN 30 is flaky"},
            )
            work_item_id = started["work_item_id"]
            status, decided = _json(base + f"/api/product/items/{work_item_id}/approve", {})
            self.assertEqual(status, 200)
            self.assertEqual(decided["decision"], "approved")
            status, done = _json(base + f"/api/product/items/{work_item_id}/resume", {})
            self.assertEqual(status, 200)
            self.assertEqual(done["state"], "done")

    def test_history_and_session_survive_pickup(self) -> None:
        with self._server() as base:
            status, hello = _json(
                base + "/api/product/ingest",
                {"channel": "web", "text": "hello"},
            )
            self.assertEqual(status, 200)
            status, milk = _json(
                base + "/api/product/ingest",
                {"channel": "web", "text": "add milk", "new": True},
            )
            self.assertEqual(status, 200)
            self.assertNotEqual(milk["thread_id"], hello["thread_id"])
            status, created = _json(base + "/api/product/threads", {"channel": "web"})
            self.assertEqual(status, 200)
            self.assertEqual(created["title"], "New chat")
            status, threads = _json(base + "/api/product/threads?channel=web")
            self.assertEqual(status, 200)
            ids = {row["thread_id"] for row in threads}
            self.assertIn(hello["thread_id"], ids)
            self.assertIn(milk["thread_id"], ids)
            self.assertIn(created["thread_id"], ids)
            status, pickup = _json(
                base + "/api/product/ingest",
                {
                    "channel": "web",
                    "text": "powerdns on VLAN 30 is flaky",
                    "thread_id": hello["thread_id"],
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(pickup["thread_id"], hello["thread_id"])
            status, convo = _json(
                base + f"/api/product/conversation?thread_id={hello['thread_id']}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(convo["thread_id"], hello["thread_id"])
            human = [turn["content"] for turn in convo["chat"] if turn["role"] == "human"]
            self.assertEqual(human, ["hello", "powerdns on VLAN 30 is flaky"])
            status, sess = _json(base + f"/api/product/session?thread_id={hello['thread_id']}")
            self.assertEqual(status, 200)
            self.assertEqual(sess["session_id"], hello["thread_id"])
            self.assertTrue(sess["traces"])
            self.assertTrue(sess["spans"])

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
