"""S1: flaky VLAN 30 PowerDNS — route, MCP reads, cloud diagnose, approve, resume."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from runbyus.common.harness import open_harness
from runbyus.langgraph.s1 import run as langgraph_s1
from runbyus.pydanticai.s1 import run as pydanticai_s1

RUNTIMES = (
    ("langgraph", langgraph_s1),
    ("pydanticai", pydanticai_s1),
)


class TestS1(unittest.TestCase):
    def test_s1_pauses_for_impactful_update(self) -> None:
        for name, run in RUNTIMES:
            with self.subTest(runtime=name):
                with open_harness() as harness:
                    item = run(harness, until="awaiting_approval")
                    self.assertEqual(item.state, "awaiting_approval")
                    routes = harness.ledger.list_routes(item.id)
                    self.assertGreaterEqual(len(routes), 2)
                    self.assertEqual(routes[0].tier, "classifier")
                    self.assertEqual(routes[0].provider, "local")
                    self.assertEqual(routes[1].provider, "anthropic")
                    tools = [
                        span["name"]
                        for span in harness.emitter.spans()
                        if span["kind"] == "tool"
                    ]
                    self.assertIn("dns_query", tools)
                    self.assertIn("pdns_get_record", tools)
                    self.assertNotIn("pdns_update_record", tools)
                    self.assertEqual(harness.pdns.update_count("vlan30.home.example"), 0)

    def test_s1_resume_after_reopen_applies_once(self) -> None:
        for name, run in RUNTIMES:
            with self.subTest(runtime=name):
                with self._file_db() as db_url:
                    with open_harness(db_url=db_url, runtime=name) as harness:
                        item = run(harness, until="awaiting_approval")
                        work_item_id = item.id
                    with open_harness(db_url=db_url, runtime=name) as harness:
                        harness.approvals.decide(
                            work_item_id, "approved", decided_by="prn_01", channel="cli"
                        )
                        done = harness.runtime.resume(
                            work_item_id,
                            harness.approvals.get_for_work_item(work_item_id),
                        )
                        self.assertEqual(done.state, "done")
                        self.assertEqual(
                            harness.pdns.update_count("vlan30.home.example"), 1
                        )
                        record = harness.pdns.pdns_get_record("vlan30.home.example")
                        self.assertFalse(record["flaky"])

    def test_s1_survives_kill_9(self) -> None:
        for name in ("langgraph", "pydanticai"):
            with self.subTest(runtime=name):
                with self._file_db() as db_url:
                    env = os.environ.copy()
                    env["RUNBYUS_DB_URL"] = db_url
                    env["RUNBYUS_RUNTIME"] = name
                    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
                    proc = subprocess.Popen(
                        [sys.executable, "-m", "runbyus.scripts.s1_until_approval"],
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    work_item_id = self._wait_for_line(proc, "AWAITING ")
                    os.kill(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
                    if proc.stdout:
                        proc.stdout.close()
                    if proc.stderr:
                        proc.stderr.close()
                    with open_harness(db_url=db_url, runtime=name) as harness:
                        paused = harness.ledger.get_work_item(work_item_id)
                        self.assertEqual(paused.state, "awaiting_approval")
                        harness.approvals.decide(
                            work_item_id, "approved", decided_by="prn_01", channel="cli"
                        )
                        done = harness.runtime.resume(
                            work_item_id,
                            harness.approvals.get_for_work_item(work_item_id),
                        )
                        self.assertEqual(done.state, "done")
                        self.assertEqual(
                            harness.pdns.update_count("vlan30.home.example"), 1
                        )

    def _wait_for_line(self, proc: subprocess.Popen, prefix: str, timeout: float = 20.0) -> str:
        assert proc.stdout is not None
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if line.startswith(prefix):
                return line.split(prefix, 1)[1].strip()
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr else ""
                self.fail(f"worker exited {proc.returncode}: {err}")
        self.fail("worker did not reach awaiting_approval")

    def _file_db(self):
        from tempfile import TemporaryDirectory

        class _Ctx:
            def __enter__(self_inner):
                self_inner.td = TemporaryDirectory()
                path = Path(self_inner.td.name) / "ledger.sqlite"
                self_inner.db_url = f"sqlite:///{path}"
                return self_inner.db_url

            def __exit__(self_inner, *exc):
                self_inner.td.cleanup()

        return _Ctx()


if __name__ == "__main__":
    unittest.main()
