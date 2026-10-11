"""Sortable IDs with a type prefix (SPEC §3.1)."""

from __future__ import annotations

import time
import uuid


def new_id(prefix: str) -> str:
    ts = format(int(time.time() * 1000), "X").zfill(10)
    rand = uuid.uuid4().hex[:16].upper()
    return f"{prefix}_{ts}{rand}"
