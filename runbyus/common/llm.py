"""OpenAI-spec (llama.cpp / vLLM) and Anthropic Messages clients."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from runbyus.common.targets import (
    CLOUD_IDS,
    DEFAULT_CLOUD,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_TARGET,
    LOCAL_TARGETS,
    TARGET_IDS,
)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class LlmResult:
    provider: str
    model: str
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class LocalTarget:
    id: str
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    extra_body: dict[str, Any] = field(default_factory=dict)


def _empty_targets() -> dict[str, LocalTarget]:
    return {
        spec.id: LocalTarget(id=spec.id, extra_body=dict(spec.extra_body))
        for spec in LOCAL_TARGETS
    }


def _secret_status(value: str) -> str:
    if not value:
        return "unset"
    if value == "PLACEHOLDER":
        return "placeholder"
    return "set"


@dataclass
class LiveConfig:
    local_base_url: str = ""
    local_model: str = ""
    local_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    cloud: str = DEFAULT_CLOUD
    selected: str = DEFAULT_TARGET
    targets: dict[str, LocalTarget] = field(default_factory=_empty_targets)

    def __post_init__(self) -> None:
        if not self.targets:
            self.targets = _empty_targets()
        if self.selected not in self.targets:
            raise ValueError(f"unknown local target {self.selected}")
        if self.cloud not in CLOUD_IDS:
            raise ValueError(f"unknown cloud provider {self.cloud}")
        pick = self.targets[self.selected]
        if self.local_base_url:
            pick.base_url = self.local_base_url
        else:
            self.local_base_url = pick.base_url
        if self.local_model:
            pick.model = self.local_model
        else:
            self.local_model = pick.model
        if self.local_api_key:
            pick.api_key = self.local_api_key
        else:
            self.local_api_key = pick.api_key

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, selected: str = DEFAULT_TARGET) -> "LiveConfig":
        src = env if env is not None else os.environ
        chosen = (src.get("RUNBYUS_LOCAL_TARGET") or selected or DEFAULT_TARGET).strip()
        if chosen not in TARGET_IDS:
            raise ValueError(f"unknown local target {chosen}")
        cloud = (src.get("RUNBYUS_CLOUD") or DEFAULT_CLOUD).strip() or DEFAULT_CLOUD
        if cloud not in CLOUD_IDS:
            raise ValueError(f"unknown cloud provider {cloud}")
        targets: dict[str, LocalTarget] = {}
        for spec in LOCAL_TARGETS:
            url = (src.get(spec.env_url) or "").strip()
            model = (src.get(spec.env_model) or "").strip()
            key = (src.get(spec.env_key) or "").strip()
            if spec.id == DEFAULT_TARGET:
                url = url or (src.get("RUNBYUS_LOCAL_BASE_URL") or "").strip()
                model = model or (src.get("RUNBYUS_LOCAL_MODEL") or "").strip()
                key = key or (src.get("RUNBYUS_LOCAL_API_KEY") or "").strip()
            targets[spec.id] = LocalTarget(
                id=spec.id,
                base_url=url,
                model=model,
                api_key=key,
                extra_body=dict(spec.extra_body),
            )
        pick = targets[chosen]
        return cls(
            local_base_url=pick.base_url,
            local_model=pick.model,
            local_api_key=pick.api_key,
            anthropic_api_key=(
                src.get("RUNBYUS_ANTHROPIC_API_KEY") or src.get("ANTHROPIC_API_KEY") or ""
            ).strip(),
            anthropic_model=(src.get("RUNBYUS_ANTHROPIC_MODEL") or "").strip(),
            anthropic_base_url=(
                src.get("RUNBYUS_ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
            ).strip(),
            openai_api_key=(src.get("RUNBYUS_OPENAI_API_KEY") or src.get("OPENAI_API_KEY") or "").strip(),
            openai_model=(src.get("RUNBYUS_OPENAI_MODEL") or "").strip(),
            openai_base_url=(src.get("RUNBYUS_OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL).strip(),
            cloud=cloud,
            selected=chosen,
            targets=targets,
        )

    def with_target(self, target_id: str) -> "LiveConfig":
        if target_id not in self.targets:
            raise ValueError(f"unknown local target {target_id}")
        pick = self.targets[target_id]
        return self._copy(selected=target_id, local_base_url=pick.base_url, local_model=pick.model, local_api_key=pick.api_key)

    def with_cloud(self, cloud: str) -> "LiveConfig":
        if cloud not in CLOUD_IDS:
            raise ValueError(f"unknown cloud provider {cloud}")
        return self._copy(cloud=cloud)

    def _copy(self, **overrides) -> "LiveConfig":
        data = dict(
            local_base_url=self.local_base_url,
            local_model=self.local_model,
            local_api_key=self.local_api_key,
            anthropic_api_key=self.anthropic_api_key,
            anthropic_model=self.anthropic_model,
            anthropic_base_url=self.anthropic_base_url,
            openai_api_key=self.openai_api_key,
            openai_model=self.openai_model,
            openai_base_url=self.openai_base_url,
            cloud=self.cloud,
            selected=self.selected,
            targets=self.targets,
        )
        data.update(overrides)
        return LiveConfig(**data)

    def target_ready(self, target_id: str) -> bool:
        pick = self.targets[target_id]
        return bool(pick.base_url and pick.model)

    def _key_ready(self, key: str, model: str) -> bool:
        return bool(model and key and key != "PLACEHOLDER")

    def _anthropic_ready(self) -> bool:
        return self._key_ready(self.anthropic_api_key, self.anthropic_model)

    def cloud_ready(self, cloud: str | None = None) -> bool:
        chosen = cloud or self.cloud
        if chosen == "openai":
            return self._key_ready(self.openai_api_key, self.openai_model)
        return self._anthropic_ready()

    def all_targets_ready(self) -> bool:
        return all(self.target_ready(target_id) for target_id in TARGET_IDS) and self._anthropic_ready()

    @property
    def ready(self) -> bool:
        return self.target_ready(self.selected) and self.cloud_ready()

    def missing(self, target: str | None = None, cloud: str | None = None) -> list[str]:
        needed: list[str] = []
        specs = {spec.id: spec for spec in LOCAL_TARGETS}
        chosen = [target] if target else list(TARGET_IDS)
        for target_id in chosen:
            spec = specs[target_id]
            pick = self.targets[target_id]
            if not pick.base_url:
                needed.append(spec.env_url)
            if not pick.model:
                needed.append(spec.env_model)
        clouds = [cloud] if cloud else list(CLOUD_IDS)
        if "anthropic" in clouds:
            if not self.anthropic_api_key or self.anthropic_api_key == "PLACEHOLDER":
                needed.append("RUNBYUS_ANTHROPIC_API_KEY")
            if not self.anthropic_model:
                needed.append("RUNBYUS_ANTHROPIC_MODEL")
        if "openai" in clouds:
            if not self.openai_api_key or self.openai_api_key == "PLACEHOLDER":
                needed.append("RUNBYUS_OPENAI_API_KEY")
            if not self.openai_model:
                needed.append("RUNBYUS_OPENAI_MODEL")
        return needed

    def public_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "local_base_url": self.local_base_url,
            "local_model": self.local_model,
            "local_api_key": "set" if self.local_api_key else "unset",
            "anthropic_api_key": _secret_status(self.anthropic_api_key),
            "anthropic_model": self.anthropic_model,
            "anthropic_base_url": self.anthropic_base_url,
            "cloud": self.cloud,
            "openai_api_key": _secret_status(self.openai_api_key),
            "openai_model": self.openai_model,
            "openai_base_url": self.openai_base_url,
            "targets": {
                target_id: {
                    "base_url": pick.base_url,
                    "model": pick.model,
                    "api_key": "set" if pick.api_key else "unset",
                }
                for target_id, pick in self.targets.items()
            },
        }


class ScriptedLlm:
    """Default runbyus path: adapters do not call a model."""

    live = False

    def complete(self, role: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmResult:
        raise RuntimeError("scripted runtime does not call complete")


def http_json(
    url: str,
    *,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float = 120,
) -> dict[str, Any]:
    body = json_dumps(json).encode("utf-8") if json is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        exc.read()
        raise RuntimeError(f"LLM HTTP {exc.code} from {url.split('?')[0]}") from None
    if not raw:
        return {}
    return json_loads(raw)


def json_dumps(value: Any) -> str:
    return json.dumps(value)


def json_loads(value: str) -> Any:
    return json.loads(value)


def openai_chat_url(base: str) -> str:
    trimmed = base.rstrip("/")
    if trimmed.endswith("/v1"):
        return f"{trimmed}/chat/completions"
    return f"{trimmed}/v1/chat/completions"


def openai_models_url(base: str) -> str:
    trimmed = base.rstrip("/")
    if trimmed.endswith("/v1"):
        return f"{trimmed}/models"
    return f"{trimmed}/v1/models"


class LlmClient:
    def __init__(self, config: LiveConfig):
        self.config = config
        self.live = True

    def complete(
        self,
        role: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LlmResult:
        if role == "local":
            extra = self.config.targets[self.config.selected].extra_body
            return self._openai_compatible(
                messages,
                tools,
                base_url=self.config.local_base_url,
                model=self.config.local_model,
                api_key=self.config.local_api_key,
                extra_body=extra,
                provider="local",
            )
        if role == "openai":
            return self._openai_compatible(
                messages,
                tools,
                base_url=self.config.openai_base_url or DEFAULT_OPENAI_BASE_URL,
                model=self.config.openai_model or DEFAULT_OPENAI_MODEL,
                api_key=self.config.openai_api_key,
                extra_body={},
                provider="openai",
            )
        if role == "anthropic":
            return self._anthropic(messages, tools)
        raise ValueError(f"unknown LLM role {role}")

    def _openai_compatible(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        base_url: str,
        model: str,
        api_key: str,
        extra_body: dict[str, Any],
        provider: str,
    ) -> LlmResult:
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": _as_openai_messages(messages),
            "tools": [_as_openai_tool(tool) for tool in tools],
        }
        payload.update(extra_body)
        data = http_json(openai_chat_url(base_url), headers=headers, json=payload)
        message = (data.get("choices") or [{}])[0].get("message") or {}
        calls = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            args = fn.get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                except json.JSONDecodeError:
                    parsed = {"_raw": args}
            else:
                parsed = args
            calls.append(ToolCall(name=fn.get("name", ""), arguments=parsed, id=raw.get("id", "")))
        return LlmResult(
            provider=provider,
            model=model,
            text=message.get("content") or "",
            tool_calls=calls,
        )

    def _anthropic(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmResult:
        headers = {
            "content-type": "application/json",
            "x-api-key": self.config.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.config.anthropic_model,
            "max_tokens": 1024,
            "messages": _as_anthropic_messages(messages),
            "tools": [_as_anthropic_tool(tool) for tool in tools],
        }
        base = self.config.anthropic_base_url.rstrip("/")
        data = http_json(f"{base}/v1/messages", headers=headers, json=payload)
        text_parts = []
        calls = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        name=block.get("name", ""),
                        arguments=block.get("input") or {},
                        id=block.get("id", ""),
                    )
                )
        return LlmResult(
            provider="anthropic",
            model=self.config.anthropic_model,
            text="".join(text_parts),
            tool_calls=calls,
        )


def tool_call_id(call: ToolCall, index: int = 0) -> str:
    return call.id or f"call_{call.name}_{index}"


def openai_assistant_with_tools(result: LlmResult, allowed: tuple[str, ...] | None = None) -> dict[str, Any]:
    calls = []
    for index, call in enumerate(result.tool_calls):
        if allowed and call.name not in allowed:
            continue
        calls.append(
            {
                "id": tool_call_id(call, index),
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments or {}),
                },
            }
        )
    return {"role": "assistant", "content": result.text or "", "tool_calls": calls}


def openai_tool_result(call: ToolCall, content: str, index: int = 0) -> dict[str, Any]:
    return {
        "role": "tool",
        "name": call.name,
        "tool_call_id": tool_call_id(call, index),
        "content": content,
    }


def _as_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for message in messages:
        role = message.get("role", "user")
        if role == "tool":
            item = {
                "role": "tool",
                "tool_call_id": message.get("tool_call_id") or message.get("name") or "tool",
                "content": message.get("content") or "",
            }
            if message.get("name"):
                item["name"] = message["name"]
            out.append(item)
        elif role == "assistant" and message.get("tool_calls"):
            content = message.get("content") or None
            if content == "":
                content = None
            out.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": message["tool_calls"],
                }
            )
        else:
            out.append({"role": role, "content": message.get("content") or ""})
    return out


def _as_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for message in messages:
        role = message.get("role", "user")
        if role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": f"Tool {message.get('name')}: {message.get('content')}",
                }
            )
        elif role == "assistant":
            out.append({"role": "assistant", "content": message.get("content") or ""})
        else:
            out.append({"role": "user", "content": message.get("content") or ""})
    if not out:
        out = [{"role": "user", "content": "Continue."}]
    # Anthropic requires alternating roles; collapse consecutive same-role.
    merged: list[dict[str, Any]] = []
    for item in out:
        if merged and merged[-1]["role"] == item["role"]:
            merged[-1]["content"] = f"{merged[-1]['content']}\n{item['content']}"
        else:
            merged.append(item)
    if merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(context)"})
    return merged


def _as_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description") or "",
            "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
        },
    }


def _as_anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool.get("description") or "",
        "input_schema": tool.get("inputSchema") or {"type": "object", "properties": {}},
    }


READ_TOOLS = ("dns_query", "pdns_get_record")
UPDATE_TOOL = "pdns_update_record"


def default_update_args(work_item_id: str) -> dict[str, Any]:
    return {
        "name": "vlan30.home.example",
        "content": "10.0.0.9",
        "idempotency_key": f"{work_item_id}:apply",
    }


def merge_update_args(work_item_id: str, incoming: dict[str, Any] | None) -> dict[str, Any]:
    args = default_update_args(work_item_id)
    if incoming:
        if incoming.get("name"):
            args["name"] = incoming["name"]
        if incoming.get("content"):
            args["content"] = incoming["content"]
    args["idempotency_key"] = f"{work_item_id}:apply"
    return args
