"""Load the runbyus policy file (SPEC §2.1 import format)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

POLICY_PATH = Path(__file__).with_name("policy.yaml")


@dataclass(frozen=True)
class Policy:
    raw: dict[str, Any]

    def space_id(self, name: str) -> str:
        return self._lookup("spaces", name)

    def label_id(self, name: str) -> str:
        return self._lookup("labels", name)

    def space_name(self, space_id: str) -> str:
        for row in self.raw["spaces"]:
            if row["id"] == space_id:
                return str(row["name"])
        raise KeyError(space_id)

    def label_name(self, label_id: str) -> str:
        for row in self.raw["labels"]:
            if row["id"] == label_id:
                return str(row["name"])
        raise KeyError(label_id)

    def allowed_models(self, space_id: str, label_id: str) -> set[str]:
        space = self.space_name(space_id)
        label = self.label_name(label_id)
        for row in self.raw.get("model_allowlists", []):
            if row["space"] == space and row["label"] == label:
                return set(row["models"])
        return set()

    def match_rules(self) -> list[dict[str, Any]]:
        return list(self.raw.get("match_rules", []))

    def _lookup(self, key: str, name: str) -> str:
        for row in self.raw[key]:
            if row["name"] == name or row["id"] == name:
                return str(row["id"])
        raise KeyError(f"{key} {name!r}")


def load_policy(path: Path | None = None) -> Policy:
    data = yaml.safe_load((path or POLICY_PATH).read_text(encoding="utf-8"))
    return Policy(raw=data)
