"""Both adapters sit behind the SPEC §8 AgentRuntime protocol."""

from __future__ import annotations

import inspect
import unittest

from unittest.mock import patch

from runbyus.common.runtime import AgentRuntime, RUNTIMES, resolve_runtime
from runbyus.langgraph.adapter import LangGraphRuntime
from runbyus.pydanticai.adapter import PydanticAIRuntime


class TestRuntimeProtocol(unittest.TestCase):
    def test_default_runtime_is_pydanticai_and_langgraph_stays(self) -> None:
        self.assertEqual(RUNTIMES, ("pydanticai", "langgraph"))
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_runtime(""), "pydanticai")
        with patch.dict("os.environ", {"RUNBYUS_RUNTIME": "langgraph"}, clear=True):
            self.assertEqual(resolve_runtime(""), "langgraph")
        self.assertEqual(resolve_runtime("langgraph"), "langgraph")

    def test_protocol_methods(self) -> None:
        names = {name for name, _ in inspect.getmembers(AgentRuntime, inspect.isfunction)}
        self.assertTrue({"start", "resume", "cancel"} <= names)

    def test_adapters_match_protocol(self) -> None:
        for cls in (LangGraphRuntime, PydanticAIRuntime):
            for method in ("start", "resume", "cancel"):
                self.assertTrue(callable(getattr(cls, method)))


if __name__ == "__main__":
    unittest.main()
