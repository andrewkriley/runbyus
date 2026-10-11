"""Public extract must not ship GLAM, house hosts, or lab names."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
SKIP_SUFFIXES = {".sqlite", ".pyc", ".png", ".jpg", ".woff", ".woff2"}

# Patterns live only in this file (the tree scan skips it) so the examples
# themselves cannot leak into the published extract.
FORBIDDEN = (
    (re.compile(r"(?i)(?:[a-z0-9-]+\.)*therileys\.team\b"), "*.therileys.team"),
    (re.compile(r"therileys", re.I), "house domain stem"),
    (re.compile(r"(?i)\bglam(?:-cp|-ai|-plan)?\b"), "GLAM / glam-cp"),
    (re.compile(r"(?i)apps/glam\b"), "house glam app path"),
    (re.compile(r"10\.54\."), "house 10.54/16"),
    (re.compile(r"infisical", re.I), "house secret store"),
    (re.compile(r"halo-granite"), "house target"),
    (re.compile(r"halo-gpt"), "house target"),
    (re.compile(r"gpu-granite"), "house target"),
    (re.compile(r"cursor-worker"), "house identity"),
    (re.compile(r"TELEGRAM_BOT_TOKEN"), "Telegram bot secret"),
    (re.compile(r"RUNBYUS_TELEGRAM"), "Telegram bot env"),
    (re.compile(r"api\.telegram\.org"), "Telegram Bot API"),
    (re.compile(r"HOUSE_LOCAL"), "house target table"),
    (re.compile(r"name:\s*Andrew\b"), "house principal"),
)

CATCH_SAMPLES = (
    ("runbyus.therileys.team", "*.therileys.team"),
    ("gitlab.home.therileys.team", "*.therileys.team"),
    ("https://infisical.home.therileys.team", "*.therileys.team"),
    ("GLAM", "GLAM / glam-cp"),
    ("glam-cp", "GLAM / glam-cp"),
    ("apps/glam/runbyus", "house glam app path"),
    ("10.54.11.25", "house 10.54/16"),
)


def _iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix in SKIP_SUFFIXES:
            continue
        if path.name == "test_public_hygiene.py":
            continue
        files.append(path)
    return files


def _hits_in(text: str) -> list[str]:
    found: list[str] = []
    for pattern, label in FORBIDDEN:
        if pattern.search(text):
            found.append(label)
    return found


class TestPublicHygiene(unittest.TestCase):
    def test_scanner_catches_glam_and_house_hosts(self) -> None:
        for sample, label in CATCH_SAMPLES:
            with self.subTest(sample=sample):
                self.assertIn(label, _hits_in(sample), f"scanner missed {sample!r}")

    def test_paths_have_no_glam_or_house_hosts(self) -> None:
        hits: list[str] = []
        for path in _iter_text_files():
            rel = path.relative_to(ROOT).as_posix()
            for label in _hits_in(rel):
                hits.append(f"{rel}: path: {label}")
        self.assertEqual(hits, [], "house detail in path:\n" + "\n".join(hits))

    def test_tree_has_no_glam_or_house_detail(self) -> None:
        hits: list[str] = []
        for path in _iter_text_files():
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
