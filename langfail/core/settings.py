"""Runtime settings store, layered over the env-based Config.

Settings live in the ``settings`` table as JSON documents keyed by a dotted
namespace (``security.strict_paths``, ``llm.model``). Env config provides the
defaults; a stored row overrides them. Dotted keys are aliases into their
namespace document: writing ``security.strict_paths`` stores the value inside
the ``security`` document, so namespace merges and dotted reads stay
consistent. This lets operators (and per-user preference endpoints) tune
behaviour without a redeploy.
"""
from __future__ import annotations

import json
from typing import Any

from .db import db


def _row(key: str):
    from ..models import Setting

    return Setting.query.filter_by(key=key).first()


def get(key: str, default: Any = None) -> Any:
    """Return the stored value for ``key``, or ``default`` when unset.

    A dotted key (``security.strict_paths``) resolves into the document stored
    under its namespace when no exact row exists.
    """
    row = _row(key)
    if row is not None:
        try:
            return json.loads(row.value_json)
        except Exception:
            return default
    if "." in key:
        namespace, _, sub = key.partition(".")
        return get_namespaced(namespace, sub, default)
    return default


def get_bool(key: str, default: bool = False) -> bool:
    """Return ``key`` coerced to bool, falling back to ``default``."""
    value = get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def set_value(key: str, value: Any, updated_by: int | None = None) -> None:
    """Store ``value`` (JSON-serialisable) under ``key``.

    Dotted keys are folded into their namespace document (see module docstring)
    so later namespace merges do not silently diverge from dotted reads.
    """
    if "." in key:
        namespace, _, sub = key.partition(".")
        merge_namespace(namespace, {sub: value}, updated_by=updated_by)
        return
    from ..models import Setting

    row = _row(key)
    if row is None:
        row = Setting(key=key)
        db.session.add(row)
    row.value_json = json.dumps(value)
    row.updated_by = updated_by
    db.session.commit()


def _merge(base: Any, patch: Any) -> Any:
    """Recursively merge ``patch`` onto ``base``: dicts merge key-by-key,
    every other type is replaced outright."""
    if isinstance(base, dict) and isinstance(patch, dict):
        out = dict(base)
        for k, v in patch.items():
            out[k] = _merge(out.get(k), v)
        return out
    return patch


def merge_namespace(namespace: str, patch: dict, updated_by: int | None = None) -> dict:
    """Deep-merge ``patch`` into the JSON document stored under ``namespace``.

    Preferences arrive as partial nested dicts (e.g. ``{"security":
    {"strict_paths": false}}``); merging rather than replacing keeps the keys
    the caller didn't mention intact.
    """
    current = get(namespace, {})
    if not isinstance(current, dict):
        current = {}
    merged = _merge(current, patch)
    set_value(namespace, merged, updated_by=updated_by)
    return merged


def get_namespaced(namespace: str, key: str, default: Any = None) -> Any:
    """Read ``key`` out of the document stored under ``namespace``."""
    doc = get(namespace, {})
    if isinstance(doc, dict) and key in doc:
        return doc[key]
    return default


# Namespaces a user preferences endpoint may write on a caller's behalf.
PREFERENCE_NAMESPACES = ("ui", "llm")


def merge_user_preferences(preferences: dict, updated_by: int | None = None) -> dict:
    """Merge a user-preferences document, restricted to caller-tunable
    namespaces (``ui``, ``llm``). Anything outside the allow-list is reported
    as rejected and left untouched.
    """
    applied: dict[str, Any] = {}
    rejected: list[str] = []
    for namespace, patch in (preferences or {}).items():
        if namespace not in PREFERENCE_NAMESPACES or not isinstance(patch, dict):
            rejected.append(str(namespace))
            continue
        applied[namespace] = merge_namespace(namespace, patch, updated_by=updated_by)
    return {"applied": applied, "rejected": rejected}
