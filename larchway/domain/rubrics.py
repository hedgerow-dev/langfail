"""Labeling rubrics: drafted by one member, released to every annotator."""
from __future__ import annotations

import sqlite3
from typing import Literal

from pydantic import BaseModel

RubricState = Literal["draft", "released"]


class Rubric(BaseModel):
    id: int
    member_id: int
    title: str
    guidance: str
    state: RubricState


class RubricShelf:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, member_id: int, title: str, guidance: str, state: RubricState) -> Rubric:
        cur = self.conn.execute(
            "INSERT INTO rubrics (member_id, title, guidance, state) VALUES (?, ?, ?, ?)",
            (member_id, title, guidance, state),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, rubric_id: int) -> Rubric | None:
        row = self.conn.execute("SELECT * FROM rubrics WHERE id = ?", (rubric_id,)).fetchone()
        return Rubric(**dict(row)) if row else None

    def get_released(self, rubric_id: int) -> Rubric | None:
        row = self.conn.execute("SELECT * FROM rubrics WHERE id = ? AND state = 'released'",
                                (rubric_id,)).fetchone()
        return Rubric(**dict(row)) if row else None
