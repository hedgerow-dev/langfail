"""Label suggestions for incoming items.

The suggester starts from a small built-in lexicon. Annotators send
amendments (text plus the label it should have had); a refit turns words that
are distinctive to an amendment into cues, which outrank the lexicon.
"""
from __future__ import annotations

import re
import sqlite3

from ..worker import handles

_LEXICON = {
    "refund": "billing", "invoice": "billing", "charge": "billing",
    "password": "access", "login": "access", "locked": "access",
    "crash": "defect", "error": "defect", "broken": "defect",
}

# Common words that say nothing about a label on their own.
_EVERYDAY = frozenset({
    "please", "thanks", "thank", "account", "customer", "should", "would", "really", "because",
    "before", "after", "around", "though", "through", "message", "number", "people", "something",
    "nothing", "anything", "always", "little", "online", "today", "yesterday", "another",
})


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


class Suggester:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def suggest(self, text: str) -> str:
        cues = {row["cue"]: row["label"] for row in self.conn.execute("SELECT cue, label FROM suggester_cues")}
        words = _words(text)
        for word in words:
            if word in cues:
                return cues[word]
        for word in words:
            if word in _LEXICON:
                return _LEXICON[word]
        return "general"

    def amend(self, member_id: int, text: str, label: str) -> int:
        cur = self.conn.execute("INSERT INTO amendments (member_id, text, label) VALUES (?, ?, ?)",
                                (member_id, text, label))
        self.conn.commit()
        return cur.lastrowid

    def vet(self, amendment_id: int) -> None:
        self.conn.execute("UPDATE amendments SET state = 'vetted' WHERE id = ?", (amendment_id,))
        self.conn.commit()

    def fold(self, rows: list[sqlite3.Row]) -> int:
        """Learn cues from amendment rows; returns how many cues are now in effect."""
        for row in rows:
            for word in _words(row["text"]):
                if len(word) >= 6 and word not in _EVERYDAY and word not in _LEXICON:
                    self.conn.execute("INSERT INTO suggester_cues (cue, label) VALUES (?, ?) "
                                      "ON CONFLICT(cue) DO UPDATE SET label = excluded.label", (word, row["label"]))
        ids = [row["id"] for row in rows]
        self.conn.executemany("UPDATE amendments SET state = 'folded' WHERE id = ?", [(i,) for i in ids])
        self.conn.commit()
        return self.conn.execute("SELECT COUNT(*) FROM suggester_cues").fetchone()[0]


@handles("suggester.refit")
def _refit(payload: dict, conn: sqlite3.Connection) -> dict:
    """Fold amendments into the suggester. Runs after each amendment arrives."""
    rows = conn.execute("SELECT id, text, label FROM amendments").fetchall()
    return {"amendments": len(rows), "cues": Suggester(conn).fold(rows)}


@handles("suggester.refit_vetted")
def _refit_vetted(payload: dict, conn: sqlite3.Connection) -> dict:
    """Fold only amendments a reviewer has vetted."""
    rows = conn.execute("SELECT id, text, label FROM amendments WHERE state = 'vetted'").fetchall()
    return {"amendments": len(rows), "cues": Suggester(conn).fold(rows)}
