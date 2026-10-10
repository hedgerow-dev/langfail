"""Checkpoints: uploaded weights files plus a short readme describing them."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from ..adapters.fs import checkpoint_file, checkpoint_root
from ..adapters.sql import contains, starts_with
from ..settings import Settings


class Checkpoint(BaseModel):
    id: int
    member_id: int
    name: str
    readme: str
    size_bytes: int
    placement: str | None = None
    created_at: str


class CheckpointVault(Protocol):
    def find(self, checkpoint_id: int) -> Checkpoint | None: ...

    def weights_path(self, checkpoint: Checkpoint) -> Path: ...

    def put(self, member_id: int, name: str, readme: str, weights: bytes) -> Checkpoint: ...

    def relabel(self, checkpoint: Checkpoint, name: str, readme: str) -> Checkpoint: ...

    def adopt(self, member_id: int, sidecar: dict, weights: bytes) -> Checkpoint: ...

    def catalog_rows(self, name: str = "", about: str = "", order: str = "created_at") -> list[dict]: ...


class DiskVault:
    """Metadata in SQLite, weights under ``<data_dir>/checkpoints``."""

    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn = conn
        self.settings = settings

    def find(self, checkpoint_id: int) -> Checkpoint | None:
        row = self.conn.execute("SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)).fetchone()
        return Checkpoint(**dict(row)) if row else None

    def weights_path(self, checkpoint: Checkpoint) -> Path:
        if checkpoint.placement:
            return checkpoint_root(self.settings) / checkpoint.placement
        return checkpoint_file(self.settings, checkpoint.id)

    def put(self, member_id: int, name: str, readme: str, weights: bytes) -> Checkpoint:
        cur = self.conn.execute(
            "INSERT INTO checkpoints (member_id, name, readme, size_bytes) VALUES (?, ?, ?, ?)",
            (member_id, name, readme, len(weights)),
        )
        self.conn.commit()
        checkpoint_file(self.settings, cur.lastrowid).write_bytes(weights)
        return self.find(cur.lastrowid)

    def relabel(self, checkpoint: Checkpoint, name: str, readme: str) -> Checkpoint:
        self.conn.execute("UPDATE checkpoints SET name = ?, readme = ? WHERE id = ?",
                          (name, readme, checkpoint.id))
        self.conn.commit()
        return self.find(checkpoint.id)

    def adopt(self, member_id: int, sidecar: dict, weights: bytes) -> Checkpoint:
        """Register a checkpoint exported from another workbench.

        Exports record where the weights sat under their checkpoints folder
        (``placement``); keeping it lets sharded layouts survive the move.
        """
        cur = self.conn.execute(
            "INSERT INTO checkpoints (member_id, name, readme, size_bytes) VALUES (?, ?, ?, ?)",
            (member_id, sidecar["name"], sidecar.get("readme", ""), len(weights)),
        )
        placement = sidecar.get("placement") or f"{cur.lastrowid}.bin"
        self.conn.execute("UPDATE checkpoints SET placement = ? WHERE id = ?", (placement, cur.lastrowid))
        self.conn.commit()
        target = checkpoint_root(self.settings) / placement
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(weights)
        return self.find(cur.lastrowid)

    def catalog_rows(self, name: str = "", about: str = "", order: str = "created_at") -> list[dict]:
        """Catalog listing: name anywhere, readme by its opening words, newest first by default."""
        clauses = ["1=1"]
        if name:
            clauses.append(contains("name", name))
        if about:
            clauses.append(starts_with("readme", about))
        statement = (
            "SELECT id, member_id, name, readme, size_bytes, placement, created_at FROM checkpoints "
            f"WHERE {' AND '.join(clauses)} ORDER BY {order} DESC LIMIT 100"
        )
        return [dict(row) for row in self.conn.execute(statement)]
