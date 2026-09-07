"""Filesystem helpers for the object store.

The store resolves object keys under a single root. These wrappers exist so call
sites read as intent (``resolve_under`` / ``read_bytes``) rather than raw
``os.path`` / ``open`` calls scattered across modules.
"""
from __future__ import annotations

from pathlib import Path


def resolve_under(root: Path, key: str) -> Path:
    """Join ``key`` onto ``root`` and return the resulting path."""
    return root.joinpath(key)


def read_bytes(path: Path) -> bytes:
    """Read a resolved path as bytes."""
    return path.read_bytes()
