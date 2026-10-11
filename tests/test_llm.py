"""OpenAI-spec (llama.cpp) and Anthropic clients, with no live network."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from runbyus.common.llm import LiveConfig, LlmClient, ScriptedLlm, ToolCall, _as_openai_messages
from runbyus.common.targets import LOCAL_TARGETS, TARGET_IDS


def _config(**overrides) -> LiveConfig:
    data = dict(
        local_base_url="http://llama.test/v1",
        local_model="granite-4.2-8b",
        local_api_key="",
        anthropic_api_key="sk-ant-test",
        anthropic_model="claude-haiku-4-5-20251001",
        anthropic_base_url="https://api.anthropic.com",
        openai_api_key="sk-openai-test",
        openai_model="gpt-4o",
        openai_base_url="https://api.openai.com/v1",
        cloud="anthropic",
    )
    data.update(overrides)
    return LiveConfig(**data)


class TestLiveConfig(unittest.TestCase):
    def test_ready_requires_local_url_model_and_anthropic_key(self) -> None:
        self.assertTrue(_config().ready)
        self.assertFalse(_config(local_base_url="").ready)
        self.assertFalse(_config(anthropic_api_key="").ready)
        self.assertFalse(_config(anthropic_api_key="PLACEHOLDER").ready)
        self.assertIn("RUNBYUS_ANTHROPIC_API_KEY", _config(anthropic_api_key="PLACEHOLDER").missing())

    def test_missing_names_do_not_include_secret_values(self) -> None:
        missing = _config(anthropic_api_key="", local_base_url="").missing()
        self.assertIn("RUNBYUS_LOCAL_BASE_URL", missing)
        self.assertIn("RUNBYUS_ANTHROPIC_API_KEY", missing)
        joined = " ".join(missing)
        self.assertNotIn("sk-ant", joined)

    def test_from_env_reads_runbyus_names(self) -> None:
        env = {
            "RUNBYUS_LOCAL_BASE_URL": "http://127.0.0.1:8000/v1",
            "RUNBYUS_LOCAL_MODEL": "local-model",
            "RUNBYUS_ANTHROPIC_API_KEY": "sk-ant-env",
            "RUNBYUS_ANTHROPIC_MODEL": "claude-sonnet-4-5",
        }
        cfg = LiveConfig.from_env(env)
        self.assertEqual(cfg.local_base_url, "http://127.0.0.1:8000/v1")
        self.assertEqual(cfg.anthropic_model, "claude-sonnet-4-5")
        self.assertTrue(cfg.ready)
        self.assertNotIn("sk-ant-env", cfg.public_dict().values())

    def test_from_env_reads_local_target(self) -> None:
        env = {
            "RUNBYUS_LOCAL_BASE_URL": "http://127.0.0.1:8000/v1",
            "RUNBYUS_LOCAL_MODEL": "local-model",
            "RUNBYUS_ANTHROPIC_API_KEY": "sk-ant-env",
            "RUNBYUS_ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
        }
        cfg = LiveConfig.from_env(env)
        self.assertEqual(set(cfg.targets), set(TARGET_IDS))
        self.assertEqual(cfg.targets["local"].model, "local-model")
        self.assertTrue(cfg.ready)
        self.assertTrue(cfg.target_ready("local"))
        self.assertNotIn("sk-ant-env", json.dumps(cfg.public_dict()))

    def test_from_env_reads_openai_cloud(self) -> None:
        env = {
            "RUNBYUS_LOCAL_BASE_URL": "http://127.0.0.1:8000/v1",
            "RUNBYUS_LOCAL_MODEL": "local-model",
            "RUNBYUS_ANTHROPIC_API_KEY": "sk-ant-env",
            "RUNBYUS_ANTHROPIC_MODEL": "claude-haiku-5-5",
            "RUNBYUS_OPENAI_API_KEY": "sk-openai-env",
            "RUNBYUS_OPENAI_MODEL": "gpt-4o",
            "RUNBYUS_OPENAI_BASE_URL": "https://api.openai.com/v1",
            "RUNBYUS_CLOUD": "openai",
        }
        cfg = LiveConfig.from_env(env)
        self.assertEqual(cfg.cloud, "openai")
        self.assertEqual(cfg.openai_model, "gpt-4o")
        self.assertTrue(cfg.cloud_ready("openai"))
        self.assertFalse(cfg.cloud_ready("openai") and "sk-openai-env" in json.dumps(cfg.public_dict()))
        self.assertEqual(cfg.public_dict()["openai_api_key"], "set")
        self.assertNotIn("sk-openai-env", json.dumps(cfg.public_dict()))

    def test_openai_placeholder_is_not_ready(self) -> None:
        cfg = _config(cloud="openai", openai_api_key="PLACEHOLDER")
        self.assertFalse(cfg.ready)
        self.assertIn("RUNBYUS_OPENAI_API_KEY", cfg.missing(cloud="openai"))
        self.assertEqual(cfg.public_dict()["openai_api_key"], "placeholder")

    def test_local_env_fills_default_target(self) -> None:
        env = {
            "RUNBYUS_LOCAL_BASE_URL": "http://127.0.0.1:8000/v1",
            "RUNBYUS_LOCAL_MODEL": "local-model",
            "RUNBYUS_ANTHROPIC_API_KEY": "sk-ant-env",
            "RUNBYUS_ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
        }
        cfg = LiveConfig.from_env(env)
        self.assertEqual(cfg.selected, "local")
        self.assertEqual(cfg.local_base_url, "http://127.0.0.1:8000/v1")
        self.assertTrue(cfg.target_ready("local"))

    def test_missing_lists_local_target(self) -> None:
        missing = LiveConfig.from_env({}).missing()
        for spec in LOCAL_TARGETS:
            self.assertIn(spec.env_url, missing)
            self.assertIn(spec.env_model, missing)
        self.assertIn("RUNBYUS_ANTHROPIC_API_KEY", missing)
        self.assertIn("RUNBYUS_ANTHROPIC_MODEL", missing)

    def test_select_target_keeps_local_endpoint(self) -> None:
        cfg = LiveConfig.from_env(
            {
                "RUNBYUS_LOCAL_BASE_URL": "http://local.test/v1",
                "RUNBYUS_LOCAL_MODEL": "local-model",
                "RUNBYUS_ANTHROPIC_API_KEY": "sk-ant-test",
                "RUNBYUS_ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
            }
        )
        selected = cfg.with_target("local")
        self.assertEqual(selected.selected, "local")
        self.assertEqual(selected.local_base_url, "http://local.test/v1")
        self.assertEqual(selected.local_model, "local-model")


class TestLlmClient(unittest.TestCase):
    def test_scripted_llm_is_not_live(self) -> None:
        llm = ScriptedLlm()
        self.assertFalse(llm.live)

    def test_openai_spec_parses_tool_calls(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "dns_query",
                                    "arguments": '{"name":"vlan30.home.example"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
        with patch("runbyus.common.llm.http_json", return_value=payload) as mocked:
            client = LlmClient(_config())
            result = client.complete(
                "local",
                [{"role": "user", "content": "powerdns on VLAN 30 is flaky"}],
                [{"name": "dns_query", "description": "query", "inputSchema": {"type": "object"}}],
            )
        self.assertEqual(result.provider, "local")
        self.assertEqual(result.model, "granite-4.2-8b")
        self.assertEqual(result.tool_calls[0].name, "dns_query")
        self.assertEqual(result.tool_calls[0].arguments["name"], "vlan30.home.example")
        url = mocked.call_args.args[0]
        self.assertTrue(url.endswith("/chat/completions"))
        body = mocked.call_args.kwargs["json"]
        self.assertEqual(body["model"], "granite-4.2-8b")
        self.assertEqual(body["tools"][0]["type"], "function")
        headers = mocked.call_args.kwargs["headers"]
        self.assertNotIn("sk-ant-test", json.dumps(headers))

    def test_anthropic_parses_tool_use(self) -> None:
        payload = {
            "content": [
                {"type": "text", "text": "replace the flaky record"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "pdns_update_record",
                    "input": {"name": "vlan30.home.example", "content": "10.0.0.9"},
                },
            ]
        }
        with patch("runbyus.common.llm.http_json", return_value=payload) as mocked:
            client = LlmClient(_config())
            result = client.complete(
                "anthropic",
                [{"role": "user", "content": "diagnose"}],
                [
                    {
                        "name": "pdns_update_record",
                        "description": "update",
                        "inputSchema": {"type": "object"},
                    }
                ],
            )
        self.assertEqual(result.provider, "anthropic")
        self.assertIn("flaky", result.text)
        self.assertEqual(result.tool_calls[0].name, "pdns_update_record")
        self.assertEqual(result.tool_calls[0].arguments["content"], "10.0.0.9")
        headers = mocked.call_args.kwargs["headers"]
        self.assertEqual(headers["x-api-key"], "sk-ant-test")
        self.assertIn("anthropic-version", headers)
        url = mocked.call_args.args[0]
        self.assertTrue(url.endswith("/v1/messages"))

    def test_openai_cloud_parses_tool_calls_and_sends_bearer(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "replace the flaky record",
                        "tool_calls": [
                            {
                                "id": "call_oa",
                                "function": {
                                    "name": "pdns_update_record",
                                    "arguments": '{"name":"vlan30.home.example","content":"10.0.0.9"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
        with patch("runbyus.common.llm.http_json", return_value=payload) as mocked:
            client = LlmClient(_config(cloud="openai"))
            result = client.complete(
                "openai",
                [{"role": "user", "content": "diagnose"}],
                [
                    {
                        "name": "pdns_update_record",
                        "description": "update",
                        "inputSchema": {"type": "object"},
                    }
                ],
            )
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "gpt-4o")
        self.assertEqual(result.tool_calls[0].name, "pdns_update_record")
        url = mocked.call_args.args[0]
        self.assertEqual(url, "https://api.openai.com/v1/chat/completions")
        headers = mocked.call_args.kwargs["headers"]
        self.assertEqual(headers["authorization"], "Bearer sk-openai-test")
        body = mocked.call_args.kwargs["json"]
        self.assertEqual(body["model"], "gpt-4o")
        self.assertEqual(body["tools"][0]["type"], "function")

    def test_openai_spec_uses_local_target_url_and_model(self) -> None:
        payload = {"choices": [{"message": {"content": "ok", "tool_calls": []}}]}
        env = {
            "RUNBYUS_LOCAL_BASE_URL": "http://127.0.0.1:8000/v1",
            "RUNBYUS_LOCAL_MODEL": "local-model",
            "RUNBYUS_ANTHROPIC_API_KEY": "sk-ant-test",
            "RUNBYUS_ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
        }
        cfg = LiveConfig.from_env(env)
        for spec in LOCAL_TARGETS:
            with self.subTest(target=spec.id), patch(
                "runbyus.common.llm.http_json", return_value=payload
            ) as mocked:
                client = LlmClient(cfg.with_target(spec.id))
                result = client.complete("local", [{"role": "user", "content": "hi"}], [])
            self.assertEqual(result.model, spec.default_model)
            url = mocked.call_args.args[0]
            self.assertTrue(url.startswith(spec.default_url.rstrip("/")))
            self.assertTrue(url.endswith("/chat/completions"))
            body = mocked.call_args.kwargs["json"]
            self.assertEqual(body["model"], spec.default_model)
            for key, value in spec.extra_body.items():
                self.assertEqual(body[key], value)

    def test_openai_followup_keeps_assistant_tool_calls_and_ids(self) -> None:
        history = [
            {"role": "user", "content": "Use dns_query on vlan30.home.example."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {
                            "name": "dns_query",
                            "arguments": '{"name":"vlan30.home.example"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "name": "dns_query",
                "tool_call_id": "call_abc",
                "content": '{"status":"SERVFAIL"}',
            },
        ]
        converted = _as_openai_messages(history)
        assistant = converted[1]
        self.assertEqual(assistant["role"], "assistant")
        self.assertIsNone(assistant["content"])
        self.assertEqual(assistant["tool_calls"][0]["id"], "call_abc")
        self.assertEqual(assistant["tool_calls"][0]["function"]["name"], "dns_query")
        tool = converted[2]
        self.assertEqual(tool["role"], "tool")
        self.assertEqual(tool["tool_call_id"], "call_abc")
        self.assertNotEqual(tool["tool_call_id"], "dns_query")

        with patch(
            "runbyus.common.llm.http_json",
            return_value={"choices": [{"message": {"content": "local reads complete"}}]},
        ) as mocked:
            LlmClient(_config()).complete("local", history, [])
        body = mocked.call_args.kwargs["json"]
        self.assertEqual(body["messages"][1]["tool_calls"][0]["id"], "call_abc")
        self.assertEqual(body["messages"][2]["tool_call_id"], "call_abc")


class TestToolCall(unittest.TestCase):
    def test_tool_call_defaults(self) -> None:
        call = ToolCall(name="dns_query", arguments={"name": "x"})
        self.assertEqual(call.name, "dns_query")


if __name__ == "__main__":
    unittest.main()
