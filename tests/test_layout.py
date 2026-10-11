"""The runbyus tree keeps the shared harness layout."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAKEOFF = ROOT / "runbyus"


class TestRunbyusLayout(unittest.TestCase):
    def test_shared_harness_paths_exist(self) -> None:
        required = [
            BAKEOFF / "common" / "ledger" / "schema.sql",
            BAKEOFF / "common" / "ledger" / "ledger.py",
            BAKEOFF / "common" / "policy.yaml",
            BAKEOFF / "common" / "router.py",
            BAKEOFF / "common" / "approvals.py",
            BAKEOFF / "common" / "emitter.py",
            BAKEOFF / "common" / "runtime.py",
            BAKEOFF / "common" / "tools" / "mock_pdns",
            BAKEOFF / "common" / "tools" / "mock_list",
            BAKEOFF / "langgraph" / "s1.py",
            BAKEOFF / "langgraph" / "s2.py",
            BAKEOFF / "langgraph" / "adapter.py",
            BAKEOFF / "pydanticai" / "s1.py",
            BAKEOFF / "pydanticai" / "s2.py",
            BAKEOFF / "pydanticai" / "adapter.py",
            BAKEOFF / "results" / "scorecard.md",
            BAKEOFF / "compose.yaml",
            BAKEOFF / "common" / "targets.py",
            BAKEOFF / "common" / "product.py",
            BAKEOFF / "web.py",
            BAKEOFF / "product" / "index.html",
            BAKEOFF / "product" / "app.js",
            BAKEOFF / "ui" / "tokens.css",
            BAKEOFF / "ui" / "style.css",
            BAKEOFF / "ui" / "design-system-source.json",
            ROOT / ".env.example",
            ROOT / "CONCEPT.md",
            ROOT / ".github" / "workflows" / "test.yml",
            ROOT / ".github" / "workflows" / "hygiene.yml",
        ]
        missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
        self.assertEqual(missing, [], f"runbyus layout missing: {missing}")

    def test_policy_covers_infra_p1_family(self) -> None:
        text = (BAKEOFF / "common" / "policy.yaml").read_text(encoding="utf-8")
        self.assertIn("infra", text)
        self.assertIn("family", text)
        self.assertIn("p1", text)
        self.assertIn("spc_", text)
        self.assertIn("prn_", text)

    def test_schema_has_spec_records(self) -> None:
        text = (BAKEOFF / "common" / "ledger" / "schema.sql").read_text(encoding="utf-8")
        for table in (
            "principal",
            "label",
            "space",
            "thread",
            "message",
            "work_item",
            "route",
            "approval",
            "event",
            "ao_trace",
            "ao_span",
        ):
            self.assertRegex(text, rf"CREATE TABLE( IF NOT EXISTS)? {table}\b")

    def test_env_example_lists_public_live_keys(self) -> None:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in (
            "RUNBYUS_LOCAL_BASE_URL",
            "RUNBYUS_LOCAL_MODEL",
            "RUNBYUS_LOCAL_API_KEY",
            "RUNBYUS_OPENAI_API_KEY",
            "RUNBYUS_OPENAI_MODEL",
            "RUNBYUS_ANTHROPIC_API_KEY",
            "RUNBYUS_ANTHROPIC_MODEL",
            "RUNBYUS_LIVE",
        ):
            self.assertIn(key, text)
        self.assertNotIn("BOT_TOKEN", text)

    def test_ui_uses_pinned_design_tokens(self) -> None:
        tokens = (BAKEOFF / "ui" / "tokens.css").read_text(encoding="utf-8")
        html = (BAKEOFF / "product" / "index.html").read_text(encoding="utf-8")
        self.assertIn("--bg-canvas: #0e1116", tokens)
        self.assertIn("assistant", html.lower())
        self.assertIn("router", html.lower())
        card = (BAKEOFF / "results" / "scorecard.md").read_text(encoding="utf-8")
        self.assertIn("Q10 = PydanticAI", card)
        self.assertIn("LangGraph stays", card)
        self.assertIn("data-product-composer", html)
        self.assertIn("data-product-history", html)
        self.assertIn("data-product-inspect", html)
        self.assertNotIn("Send to both", html)
        source = (BAKEOFF / "ui" / "design-system-source.json").read_text(encoding="utf-8")
        self.assertIn("design-system", source)
        self.assertIn("v0.1.0", source)
        self.assertNotIn("tokenSet", source)

    def test_hygiene_workflow_runs_public_scan(self) -> None:
        text = (ROOT / ".github" / "workflows" / "hygiene.yml").read_text(encoding="utf-8")
        self.assertIn("tests.test_public_hygiene", text)
        self.assertIn("Forbidden house hosts", text)

    def test_compose_runs_postgres_for_ledger(self) -> None:
        text = (BAKEOFF / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("postgres", text.lower())
        self.assertIn("schema.sql", text)


if __name__ == "__main__":
    unittest.main()
