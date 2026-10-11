"""OpenAI-spec listeners used by the runbyus live path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TargetSpec:
    id: str
    env_url: str
    env_model: str
    env_key: str
    default_url: str
    default_model: str
    extra_body: dict[str, Any]
    alias: str = ""


LOCAL_TARGETS: tuple[TargetSpec, ...] = (
    TargetSpec(
        id="local",
        env_url="RUNBYUS_LOCAL_BASE_URL",
        env_model="RUNBYUS_LOCAL_MODEL",
        env_key="RUNBYUS_LOCAL_API_KEY",
        default_url="http://127.0.0.1:8000/v1",
        default_model="local-model",
        extra_body={},
    ),
)

TARGET_IDS = tuple(spec.id for spec in LOCAL_TARGETS)
DEFAULT_TARGET = "local"

CLOUD_IDS = ("anthropic", "openai")
DEFAULT_CLOUD = "anthropic"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o"
