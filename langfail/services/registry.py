"""Artifact storage for the model registry.

Artifacts live under ARTIFACT_DIR; each model row references its artifact by a
relative name. Reads go through :func:`langfail.core.security.sanitize_path` to keep
access within the storage root.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..core.config import ARTIFACT_DIR
from ..core.security import sanitize_path


def store_artifact(name: str, data: bytes) -> str:
    """Persist raw artifact bytes and return the stored relative name."""
    safe = sanitize_path(name)
    path = ARTIFACT_DIR / safe
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return str(path)


def read_artifact(name: str) -> bytes:
    """Read an artifact by its relative name."""
    safe = sanitize_path(name)
    with open(os.path.join(str(ARTIFACT_DIR), safe), "rb") as fh:
        return fh.read()


def read_raw(name: str) -> bytes:
    """Read an artifact by name relative to the registry root.

    Callers are expected to have normalised ``name`` upstream according to the
    deployment's path policy (see ``STRICT_PATHS``).
    """
    with open(os.path.join(str(ARTIFACT_DIR), name), "rb") as fh:
        return fh.read()


def read_artifact_safe(name: str) -> bytes:
    """Read an artifact, refusing any path that escapes the registry root.

    The resolved real path must stay within ARTIFACT_DIR, so traversal and
    absolute paths are rejected regardless of how ``name`` was formed.
    """
    root = os.path.realpath(str(ARTIFACT_DIR))
    target = os.path.realpath(os.path.join(root, name))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("path escapes registry root")
    with open(target, "rb") as fh:
        return fh.read()


def save_with_metadata(data: bytes, meta: dict) -> str:
    """Persist an artifact to a location described by its metadata.

    Export tooling records a preferred ``storage_path`` (relative to the
    registry root) so re-imported bundles keep their original layout.
    """
    rel = meta.get("storage_path") or f"{meta.get('name', 'model')}.bin"
    target = os.path.join(str(ARTIFACT_DIR), rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as fh:
        fh.write(data)
    meta["_resolved_path"] = target
    return json.dumps(meta)
