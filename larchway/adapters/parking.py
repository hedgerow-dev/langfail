"""Short-lived values parked between requests (captions, drafts).

Slots hold compressed, text-encoded JSON so any JSON value fits one slot and
large drafts stay small in memory.
"""
from __future__ import annotations

import base64
import json
import zlib
from typing import Any

_PARKED: dict[str, str] = {}


def park(key: str, value: Any) -> None:
    _PARKED[key] = base64.b85encode(zlib.compress(json.dumps(value).encode())).decode()


def held(key: str) -> Any | None:
    raw = _PARKED.get(key)
    if raw is None:
        return None
    return json.loads(zlib.decompress(base64.b85decode(raw)))
