"""Public extract must not ship house hosts, secrets, or lab names."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
SKIP_SUFFIXES = {".sqlite", ".pyc", ".png", ".jpg", ".woff", ".woff2"}

FORBIDDEN = (
    (re.compile(r"10\.54\.10"), "lab Halo listener"),
    (re.compile(r"10\.54\.11"), "lab GPU listener"),
    (re.compile(r"therileys", re.I), "house domain"),
    (re.compile(r"infisical", re.I), "house secret store"),
    (re.compile(r"halo-granite"), "house target"),
    (re.compile(r"halo-gpt"), "house target"),
    (re.compile(r"gpu-granite"), "house target"),
    (re.compile(r"glam-cp"), "house repo"),
    (re.compile(r"cursor-worker"), "house identity"),
    (re.compile(r"TELEGRAM_BOT_TOKEN"), "Telegram bot secret"),
    (re.compile(r"RUNBYUS_TELEGRAM"), "Telegram bot env"),
    (re.compile(r"api\.telegram\.org"), "Telegram Bot API"),
    (re.compile(r"HOUSE_LOCAL"), "house target table"),
    (re.compile(r"name:\s*Andrew\b"), "house principal"),
)


class TestPublicHygiene(unittest.TestCase):
    def test_tree_has_no_house_detail(self) -> None:
        hits: list[str] = []
        for path in ROOT.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if not path.is_file() or path.suffix in SKIP_SUFFIXES:
                continue
            if path.name == "test_public_hygiene.py":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(ROOT).as_posix()
            for pattern, label in FORBIDDEN:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    hits.append(f"{rel}:{line}: {label}")
        self.assertEqual(hits, [], "house detail leaked:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
