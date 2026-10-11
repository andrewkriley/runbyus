"""Operator CLI: run, approve, resume, show, doctor — no live network."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from runbyus.cli import main
from runbyus.common.llm import LiveConfig


class TestCli(unittest.TestCase):
    def test_doctor_reports_missing_without_secret_values(self) -> None:
        import os

        env = {k: v for k, v in os.environ.items() if not k.startswith("RUNBYUS_")}
        env["RUNBYUS_ANTHROPIC_API_KEY"] = "sk-ant-should-not-print"
        buf = io.StringIO()
        with patch.dict("os.environ", env, clear=True), redirect_stdout(buf):
            code = main(["doctor"])
        out = buf.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("RUNBYUS_LOCAL_BASE_URL", out)
        self.assertIn("RUNBYUS_LOCAL_MODEL", out)
        self.assertNotIn("sk-ant-should-not-print", out)

    def test_run_defaults_to_pydanticai_and_keeps_langgraph(self) -> None:
        import os

        base = {k: v for k, v in os.environ.items() if k != "RUNBYUS_RUNTIME"}
        with TemporaryDirectory() as td:
            db = f"sqlite:///{Path(td) / 'ledger.sqlite'}"
            buf = io.StringIO()
            with patch.dict("os.environ", base, clear=True), redirect_stdout(buf):
                code = main(["run", "s1", "--db", db])
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(payload["runtime"], "pydanticai")
        with TemporaryDirectory() as td:
            db = f"sqlite:///{Path(td) / 'ledger.sqlite'}"
            buf = io.StringIO()
            env = dict(base)
            env["RUNBYUS_RUNTIME"] = "langgraph"
            with patch.dict("os.environ", env, clear=True), redirect_stdout(buf):
                code = main(["run", "s1", "--db", db])
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(payload["runtime"], "langgraph")

    def test_run_s1_scripted_then_approve_and_resume(self) -> None:
        with TemporaryDirectory() as td:
            db = f"sqlite:///{Path(td) / 'ledger.sqlite'}"
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["run", "s1", "--runtime", "langgraph", "--db", db])
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(payload["state"], "awaiting_approval")
            work_item_id = payload["work_item_id"]
            self.assertTrue(work_item_id.startswith("wi_"))

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["approve", work_item_id, "--db", db])
            self.assertEqual(code, 0)
            self.assertIn("approved", buf.getvalue())

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["resume", "--runtime", "langgraph", "--work-item", work_item_id, "--db", db])
            self.assertEqual(code, 0)
            done = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(done["state"], "done")

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["show", work_item_id, "--db", db])
            shown = json.loads(buf.getvalue())
            self.assertEqual(shown["state"], "done")
            self.assertGreaterEqual(len(shown["routes"]), 2)

    def test_run_s2_both_runtimes(self) -> None:
        for runtime in ("langgraph", "pydanticai"):
            with self.subTest(runtime=runtime), TemporaryDirectory() as td:
                db = f"sqlite:///{Path(td) / 'ledger.sqlite'}"
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = main(["run", "s2", "--runtime", runtime, "--db", db])
                self.assertEqual(code, 0)
                payload = json.loads(buf.getvalue().strip().splitlines()[-1])
                self.assertEqual(payload["state"], "done")
                self.assertEqual(payload["scenario"], "s2")

    def test_live_refuses_when_config_incomplete(self) -> None:
        buf = io.StringIO()
        with patch.object(LiveConfig, "from_env", return_value=LiveConfig.from_env({})), redirect_stdout(buf):
            code = main(["run", "s1", "--runtime", "pydanticai", "--live"])
        self.assertEqual(code, 2)
        self.assertIn("RUNBYUS_LOCAL_BASE_URL", buf.getvalue())

    def test_live_openai_cloud_requires_key(self) -> None:
        buf = io.StringIO()
        with patch.object(LiveConfig, "from_env", return_value=LiveConfig.from_env({})), redirect_stdout(
            buf
        ):
            code = main(
                ["run", "s1", "--runtime", "pydanticai", "--live", "--target", "local", "--cloud", "openai"]
            )
        self.assertEqual(code, 2)
        self.assertIn("RUNBYUS_OPENAI_API_KEY", buf.getvalue())

    def test_live_target_flag_requires_that_endpoint(self) -> None:
        buf = io.StringIO()
        with patch.object(LiveConfig, "from_env", return_value=LiveConfig.from_env({})), redirect_stdout(
            buf
        ):
            code = main(["run", "s1", "--runtime", "pydanticai", "--live", "--target", "local"])
        self.assertEqual(code, 2)
        self.assertIn("RUNBYUS_LOCAL_BASE_URL", buf.getvalue())

    def test_doctor_reports_local_target(self) -> None:
        import os

        env = {k: v for k, v in os.environ.items() if not k.startswith("RUNBYUS_")}
        env.update(
            {
                "RUNBYUS_LOCAL_BASE_URL": "http://local.test/v1",
                "RUNBYUS_LOCAL_MODEL": "local-model",
                "RUNBYUS_ANTHROPIC_API_KEY": "sk-ant-should-not-print",
                "RUNBYUS_ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
            }
        )
        buf = io.StringIO()
        with (
            patch.dict("os.environ", env, clear=True),
            patch("runbyus.common.operator.http_json", return_value={"data": []}),
            redirect_stdout(buf),
        ):
            code = main(["doctor"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("local", out)
        self.assertIn("openai", out)
        self.assertNotIn("sk-ant-should-not-print", out)

    def test_ui_help_exposes_bind_flags(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit):
            main(["ui", "--help"])
        out = buf.getvalue()
        self.assertIn("--host", out)
        self.assertIn("--port", out)


if __name__ == "__main__":
    unittest.main()
