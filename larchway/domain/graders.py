"""Graders: serialized scoring estimators teams register and run against samples.

Metadata lives in SQLite; the artifact bytes live under ``<data_dir>/graders``.
A grader is reconstructed lazily the first time it is asked to score, and the
reconstructed estimator is cached per process.
"""
from __future__ import annotations

import base64
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from ..adapters import codecs, outbound
from ..settings import Settings
from ..worker import handles


class Grader(BaseModel):
    id: int
    member_id: int
    name: str
    runtime: str
    blob_path: str | None = None
    created_at: str


class GraderShelf(Protocol):
    def find(self, grader_id: int) -> Grader | None: ...

    def register(self, member_id: int, name: str, runtime: str, artifact: bytes) -> Grader: ...

    def estimator(self, grader: Grader) -> Any: ...

    def raw(self, grader: Grader) -> bytes: ...


class DiskGraders:
    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn = conn
        self.settings = settings

    def _root(self) -> Path:
        return self.settings.data_dir / "graders"

    def find(self, grader_id: int) -> Grader | None:
        row = self.conn.execute("SELECT * FROM graders WHERE id = ?", (grader_id,)).fetchone()
        return Grader(**dict(row)) if row else None

    def register(self, member_id: int, name: str, runtime: str, artifact: bytes) -> Grader:
        cur = self.conn.execute(
            "INSERT INTO graders (member_id, name, runtime) VALUES (?, ?, ?)",
            (member_id, name, runtime),
        )
        path = self._root() / f"{cur.lastrowid}.bin"
        path.write_bytes(artifact)
        self.conn.execute("UPDATE graders SET blob_path = ? WHERE id = ?", (str(path), cur.lastrowid))
        self.conn.commit()
        return self.find(cur.lastrowid)

    def estimator(self, grader: Grader) -> Any:
        return codecs.revive(grader.blob_path, grader.runtime)

    def raw(self, grader: Grader) -> bytes:
        return Path(grader.blob_path).read_bytes()


def _resembles_artifact(name: str, data: bytes) -> bool:
    return name.endswith((".pkl", ".pt", ".joblib", ".bin")) or data[:2] == b"\x80\x04"


@handles("grader.call")
def _run_batch_call(payload: dict, conn: sqlite3.Connection) -> dict:
    """Apply a batched method call delivered over the work queue to a grader."""
    call = codecs.decode_call(base64.b64decode(payload["call_b64"]))
    return {"grader_id": payload.get("grader_id"), "call": str(call)[:80]}


@handles("grader.pull")
def _pull_remote(payload: dict, conn: sqlite3.Connection) -> dict:
    """Import a grader artifact referenced by URL into the local registry."""
    row = conn.execute("SELECT * FROM graders WHERE id = ?", (payload["grader_id"],)).fetchone()
    if row is None:
        return {"error": "no such grader"}
    blob = outbound.fetch(payload["source_url"])
    name = payload["source_url"].rstrip("/").split("/")[-1] or "download.bin"
    root = Path(row["blob_path"]).parent if row["blob_path"] else None
    dest = (root or (Path.cwd())) / f"{row['id']}.bin"
    dest.write_bytes(blob)
    conn.execute("UPDATE graders SET blob_path = ? WHERE id = ?", (str(dest), row["id"]))
    conn.commit()
    reconstructed = None
    if _resembles_artifact(name, blob):
        reconstructed = type(codecs.revive_bytes(blob, row["runtime"])).__name__
    return {"grader_id": row["id"], "reconstructed": reconstructed}
