"""Collection intakes: bulk-load prompts into a collection from a file or a URL.

A request records the intake and queues it; the worker reads the file (or
downloads it), adds one item per line (``prompt<TAB>reference``), and
announces completion so the submitter's callback can be told.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from ..adapters import outbound, shell
from ..events import emit, on
from ..worker import handles
from .collections import CollectionDesk


def record_intake(conn: sqlite3.Connection, collection_id: int, member_id: int, stored_path: Path,
                  source_url: str | None, callback_url: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO intakes (collection_id, member_id, stored_path, source_url, callback_url) "
        "VALUES (?, ?, ?, ?, ?)",
        (collection_id, member_id, str(stored_path), source_url, callback_url),
    )
    conn.commit()
    return cur.lastrowid


@handles("collection.intake")
def _load_intake(payload: dict, conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT intakes.*, collections.name AS collection_name FROM intakes "
        "JOIN collections ON collections.id = intakes.collection_id WHERE intakes.id = ?",
        (payload["intake_id"],),
    ).fetchone()
    if row is None:
        return {"error": "no such intake"}
    path = Path(row["stored_path"])
    if row["source_url"]:
        path.write_bytes(outbound.fetch_public(row["source_url"]))
    desk = CollectionDesk(conn)
    for line in path.read_text(errors="replace").splitlines():
        prompt, _, reference = line.partition("\t")
        if prompt.strip():
            desk.add_item(row["collection_id"], prompt, reference)
    lines = shell.count_lines(path, row["collection_name"])
    conn.execute("UPDATE intakes SET state = 'loaded', line_count = ? WHERE id = ?", (lines, row["id"]))
    conn.commit()
    asyncio.run(emit("collection.intake_loaded", {
        "intake_id": row["id"], "collection_id": row["collection_id"],
        "callback_url": row["callback_url"], "lines": lines,
    }))
    return {"intake_id": row["id"], "lines": lines}


@on("collection.intake_loaded")
async def _call_back(payload: dict) -> None:
    if payload.get("callback_url"):
        await outbound.post_json(payload["callback_url"], {
            "intake_id": payload["intake_id"], "collection_id": payload["collection_id"],
            "lines": payload["lines"], "state": "loaded",
        })
