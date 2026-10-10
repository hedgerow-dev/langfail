"""Annotator journals: private working notes kept alongside labeling work."""
from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel

from .members import Member


class JournalEntry(BaseModel):
    id: int
    member_id: int
    heading: str
    text: str
    updated_at: str


class Journal:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def entry(self, entry_id: int) -> JournalEntry | None:
        row = self.conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        return JournalEntry(**dict(row)) if row else None

    def entry_of(self, entry_id: int, member_id: int) -> JournalEntry | None:
        row = self.conn.execute("SELECT * FROM journal_entries WHERE id = ? AND member_id = ?",
                                (entry_id, member_id)).fetchone()
        return JournalEntry(**dict(row)) if row else None

    def entries_for(self, member_id: int) -> list[JournalEntry]:
        rows = self.conn.execute("SELECT * FROM journal_entries WHERE member_id = ? ORDER BY updated_at DESC, id DESC",
                                 (member_id,)).fetchall()
        return [JournalEntry(**dict(row)) for row in rows]

    def add(self, member_id: int, heading: str, text: str) -> JournalEntry:
        cur = self.conn.execute(
            "INSERT INTO journal_entries (member_id, heading, text) VALUES (?, ?, ?)",
            (member_id, heading, text),
        )
        self.conn.commit()
        return self.entry(cur.lastrowid)

    def rewrite(self, entry: JournalEntry, heading: str, text: str) -> JournalEntry:
        self.conn.execute(
            "UPDATE journal_entries SET heading = ?, text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (heading, text, entry.id),
        )
        self.conn.commit()
        return self.entry(entry.id)


class EntryExport:
    """Renders a journal entry as a downloadable document."""

    def __init__(self, viewer: Member):
        self.viewer = viewer

    def render(self, entry: JournalEntry, fmt: str) -> tuple[str, str]:
        """Return (media type, body)."""
        return getattr(self, f"_render_{fmt}")(entry)

    def _render_text(self, entry: JournalEntry) -> tuple[str, str]:
        return "text/plain", f"{entry.heading}\n\n{entry.text}\n"

    def _render_archive(self, entry: JournalEntry) -> tuple[str, str]:
        if entry.member_id != self.viewer.id:
            raise PermissionError(entry.id)
        return "application/json", json.dumps({"exported_by": self.viewer.handle, **entry.model_dump()})
