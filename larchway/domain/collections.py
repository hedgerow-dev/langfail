"""Collections: shared sets of prompts with reference answers, edited by collaborators."""
from __future__ import annotations

import sqlite3

from pydantic import BaseModel


class CollectionItem(BaseModel):
    id: int
    collection_id: int
    prompt: str
    reference: str


class CollectionDesk:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, name: str, creator_id: int) -> int:
        cur = self.conn.execute("INSERT INTO collections (name, created_by) VALUES (?, ?)", (name, creator_id))
        self.conn.execute("INSERT INTO collaborators (collection_id, member_id) VALUES (?, ?)",
                          (cur.lastrowid, creator_id))
        self.conn.commit()
        return cur.lastrowid

    def collaborators(self, collection_id: int) -> set[int]:
        rows = self.conn.execute("SELECT member_id FROM collaborators WHERE collection_id = ?", (collection_id,))
        return {r["member_id"] for r in rows}

    def invite(self, collection_id: int, member_id: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO collaborators (collection_id, member_id) VALUES (?, ?)",
                          (collection_id, member_id))
        self.conn.commit()

    def add_item(self, collection_id: int, prompt: str, reference: str) -> CollectionItem:
        cur = self.conn.execute(
            "INSERT INTO collection_items (collection_id, prompt, reference) VALUES (?, ?, ?)",
            (collection_id, prompt, reference),
        )
        self.conn.commit()
        return self.item(cur.lastrowid)

    def items_in(self, collection_id: int) -> list[CollectionItem]:
        rows = self.conn.execute("SELECT * FROM collection_items WHERE collection_id = ? ORDER BY id",
                                 (collection_id,))
        return [CollectionItem(**dict(r)) for r in rows]

    def item(self, item_id: int) -> CollectionItem | None:
        row = self.conn.execute("SELECT * FROM collection_items WHERE id = ?", (item_id,)).fetchone()
        return CollectionItem(**dict(row)) if row else None
