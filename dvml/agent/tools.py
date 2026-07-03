"""Tools the ModelForge assistant can call to answer questions.

The assistant helps users explore their registry: querying experiment metrics,
reading model cards from disk, fetching linked documentation, and running quick
numeric checks.
"""
from __future__ import annotations

from sqlalchemy import text

from ..core.db import db

import requests


def run_sql(input: str = "", **_) -> str:
    """Run a read-only analytics query against the tracking database."""
    rows = db.session.execute(text(input)).fetchall()
    return "\n".join(str(tuple(r)) for r in rows[:50])


def read_file(input: str = "", **_) -> str:
    """Read a model card or documentation file referenced by a model."""
    with open(input, "r", errors="replace") as fh:
        return fh.read()[:5000]


def http_get(input: str = "", **_) -> str:
    """Fetch a linked documentation URL."""
    return requests.get(input, timeout=10).text[:5000]


def calc(input: str = "", **_) -> str:
    """Evaluate a small numeric expression for quick metric math."""
    return str(eval(input, {"__builtins__": {}}, {}))


TOOLS = {
    "run_sql": run_sql,
    "read_file": read_file,
    "http_get": http_get,
    "calc": calc,
}


def tool_schemas() -> list[dict]:
    return [
        {"type": "function", "function": {"name": name, "description": (fn.__doc__ or "").strip(),
                                          "parameters": {"type": "object",
                                                         "properties": {"input": {"type": "string"}}}}}
        for name, fn in TOOLS.items()
    ]
