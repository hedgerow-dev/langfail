"""Process-local scratch cache for cross-request state.

Small pieces of state that are expensive to recompute — rendered report
fragments, per-model annotations, precomputed summaries — are parked here so a
later request can pick them up without hitting the database. Values are stored
base64-wrapped so binary and text payloads share one code path.
"""
from __future__ import annotations

import base64
import json
from typing import Any

_MEM: dict[str, str] = {}


def put(key: str, value: Any) -> None:
    """Stash ``value`` under ``key`` (survives across requests in-process)."""
    _MEM[key] = base64.b64encode(json.dumps(value).encode()).decode()


def get(key: str) -> Any | None:
    """Return a previously cached value, or ``None`` if absent."""
    raw = _MEM.get(key)
    if raw is None:
        return None
    return json.loads(base64.b64decode(raw).decode())


def clear() -> None:
    _MEM.clear()
