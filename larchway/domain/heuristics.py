"""Labeling heuristics: small functions that propose a label for an item's text.

A heuristic is saved once and applied later to batches of items. Python
heuristics define ``label(text)`` returning a label or None; keyword rules are
``keyword => label`` lines, first match wins.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from pydantic import BaseModel

Labeler = Callable[[str], "str | None"]


class Heuristic(BaseModel):
    id: int
    member_id: int
    name: str
    source: str
    created_at: str


class HeuristicShelf:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, member_id: int, name: str, source: str) -> Heuristic:
        cur = self.conn.execute("INSERT INTO heuristics (member_id, name, source) VALUES (?, ?, ?)",
                                (member_id, name, source))
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, heuristic_id: int) -> Heuristic | None:
        row = self.conn.execute("SELECT * FROM heuristics WHERE id = ?", (heuristic_id,)).fetchone()
        return Heuristic(**dict(row)) if row else None


def compile_heuristic(source: str, trust_source: bool = True) -> Labeler:
    """Build the ``label`` function a Python heuristic defines."""
    if not trust_source:
        raise PermissionError("python heuristics are turned off for this workspace")
    namespace: dict = {}
    exec(compile(source, "<heuristic>", "exec"), namespace)
    return namespace.get("label") or (lambda text: None)


def keyword_rules(source: str) -> Labeler:
    """Read ``keyword => label`` lines; anything else in the source is ignored."""
    rules = []
    for line in source.splitlines():
        keyword, sep, label = line.partition("=>")
        if sep and keyword.strip() and label.strip():
            rules.append((keyword.strip().lower(), label.strip()))

    def label(text: str) -> str | None:
        lowered = text.lower()
        return next((found for keyword, found in rules if keyword in lowered), None)

    return label
