"""Object blob storage for the registry.

Objects live under ``OBJECT_ROOT``; each artifact row references its blob by a
relative key. Reads reduce the key with
:func:`modelbay.core.naming.normalize_name` to keep access under the root.
"""
from __future__ import annotations

import json
import os

from ..core.config import OBJECT_ROOT
from ..core.naming import normalize_name
from .paths import read_bytes, resolve_under


def save_object(key: str, data: bytes) -> str:
    """Persist blob bytes under the object root; return the path written."""
    safe = normalize_name(key)
    path = resolve_under(OBJECT_ROOT, safe)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def load_object(key: str) -> bytes:
    """Read an object blob by its relative key."""
    safe = normalize_name(key)
    return read_bytes(resolve_under(OBJECT_ROOT, safe))


def read_unchecked(key: str) -> bytes:
    """Read a blob by key relative to the registry root.

    Callers are expected to have normalised ``key`` upstream according to the
    deployment's naming policy (see ``PIN_OBJECT_NAMES``).
    """
    return read_bytes(resolve_under(OBJECT_ROOT, key))


def save_with_meta(data: bytes, meta: dict) -> str:
    """Persist a blob to a location described by its metadata.

    Export tooling records a preferred ``storage_path`` (relative to the
    registry root) so re-imported bundles keep their original layout.
    """
    rel = meta.get("storage_path") or f"{meta.get('name', 'bundle')}.bin"
    target = resolve_under(OBJECT_ROOT, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    meta["_resolved_path"] = str(target)
    return json.dumps(meta)


def read_within_root(key: str) -> bytes:
    """Read an object blob, refusing any key that escapes the object root.

    The resolved real path must stay within ``OBJECT_ROOT``, so traversal and
    absolute keys are rejected however ``key`` was formed.
    """
    root = os.path.realpath(str(OBJECT_ROOT))
    target = os.path.realpath(os.path.join(root, key))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("key escapes object root")
    with open(target, "rb") as fh:
        return fh.read()
