"""Workspace-wide settings, stored as one JSON document per namespace.

Operators tune behaviour here at runtime (``storage``, ``display``,
``copilot``); values in a stored document override the defaults that come from
``Settings``.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from pydantic import BaseModel

# Namespaces a member may tune for themselves from the labeling view.
PERSONAL_NAMESPACES = ("display", "copilot")


class Flags(BaseModel):
    """Storage behaviour switches, resolved per request."""

    confine_reads: bool = False


def _overlay(base: Any, patch: Any) -> Any:
    """Lay ``patch`` over ``base``: nested objects combine key by key, anything else is replaced."""
    if not (isinstance(base, dict) and isinstance(patch, dict)):
        return patch
    combined = dict(base)
    for key, value in patch.items():
        combined[key] = _overlay(base.get(key), value)
    return combined


class SettingsBook:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def document(self, namespace: str) -> dict:
        row = self.conn.execute("SELECT document FROM workspace_settings WHERE namespace = ?",
                                (namespace,)).fetchone()
        return json.loads(row["document"]) if row else {}

    def merge(self, namespace: str, patch: dict) -> dict:
        """Combine ``patch`` into the namespace's document, keeping keys it does not mention."""
        combined = _overlay(self.document(namespace), patch)
        self.conn.execute(
            "INSERT INTO workspace_settings (namespace, document) VALUES (?, ?) "
            "ON CONFLICT(namespace) DO UPDATE SET document = excluded.document",
            (namespace, json.dumps(combined)),
        )
        self.conn.commit()
        return combined

    def merge_field(self, namespace: str, key: str, raw: str) -> dict:
        """Set one key from a form field: JSON literals (true, 30, "x") are decoded, other text is kept as is."""
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        return self.merge(namespace, {key: value})

    def merge_personal(self, areas: dict) -> tuple[dict, list[str]]:
        """Merge only the namespaces a member may tune; report the rest as refused."""
        merged: dict[str, dict] = {}
        refused: list[str] = []
        for namespace, patch in areas.items():
            if namespace in PERSONAL_NAMESPACES and isinstance(patch, dict):
                merged[namespace] = self.merge(namespace, patch)
            else:
                refused.append(namespace)
        return merged, refused
