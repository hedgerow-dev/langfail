"""Background work backed by the ``work_items`` table.

Declare a handler for a kind of work::

    @handles("collections.reindex")
    def reindex(payload: dict, conn: sqlite3.Connection) -> dict | None: ...

Request code calls ``schedule(conn, kind, payload)``; the worker process
(``larchway drain``) or a test calls ``drain_once(conn)`` to run the oldest
pending item.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable

HANDLERS: dict[str, Callable[[dict, sqlite3.Connection], object]] = {}


def handles(kind: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        HANDLERS[kind] = fn
        return fn

    return register


def schedule(conn: sqlite3.Connection, kind: str, payload: dict, member_id: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO work_items (kind, payload, member_id) VALUES (?, ?, ?)",
        (kind, json.dumps(payload), member_id),
    )
    conn.commit()
    return cur.lastrowid


def drain_once(conn: sqlite3.Connection) -> int | None:
    """Run the oldest pending item. Returns its id, or None if the queue is empty."""
    row = conn.execute(
        "SELECT id, kind, payload FROM work_items WHERE state = 'pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE work_items SET state = 'running' WHERE id = ?", (row["id"],))
    conn.commit()

    handler = HANDLERS.get(row["kind"])
    if handler is None:
        state, outcome = "failed", {"error": f"no handler for {row['kind']}"}
    else:
        try:
            state, outcome = "done", handler(json.loads(row["payload"]), conn)
        except Exception as exc:
            state, outcome = "failed", {"error": str(exc)}
    conn.execute(
        "UPDATE work_items SET state = ?, outcome = ? WHERE id = ?",
        (state, json.dumps(outcome), row["id"]),
    )
    conn.commit()
    return row["id"]
