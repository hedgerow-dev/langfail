"""Process-local scratch space for cross-request state.

Small pieces of state that are expensive to recompute -- rendered report
fragments, per-bundle annotations, precomputed summaries -- are parked here so
a later request can pick them up without hitting the database. Values are
stored base64-wrapped so binary and text payloads share one code path.
"""
from __future__ import annotations

import base64
import json
from typing import Any

_SLOTS: dict[str, str] = {}


def stash(key: str, value: Any) -> None:
    """Park ``value`` under ``key`` (survives across requests in-process)."""
    _SLOTS[key] = base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def recall(key: str) -> Any | None:
    """Return a previously parked value, or ``None`` if absent."""
    raw = _SLOTS.get(key)
    if raw is None:
        return None
    return json.loads(base64.urlsafe_b64decode(raw.encode()).decode())


def drop_all() -> None:
    _SLOTS.clear()
