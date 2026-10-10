"""Evaluation runs and the per-sample verdicts recorded against them."""
from __future__ import annotations

import sqlite3
from typing import Literal, Protocol

from pydantic import BaseModel

from ..adapters import shell
from ..worker import handles


class EvalRun(BaseModel):
    id: int
    member_id: int
    name: str
    label: str
    created_at: str


class Verdict(BaseModel):
    id: int
    run_id: int
    sample: str
    score: float
    rationale: str


RUN_COLUMNS = "id, member_id, name, label, created_at"


class FieldFilter(BaseModel):
    field: Literal["name", "label"]
    value: str


class RunLedger(Protocol):
    def open_run(self, member_id: int, name: str, label: str) -> EvalRun: ...

    def run(self, run_id: int) -> EvalRun | None: ...

    def member_run(self, run_id: int, member_id: int) -> EvalRun | None: ...

    def total_for(self, member_ref: str) -> int: ...

    def with_label(self, label: str) -> list[EvalRun]: ...

    def runs_of(self, member_id: int, order: str) -> list[EvalRun]: ...

    def where(self, member_id: int, condition: str) -> list[dict]: ...

    def by_field(self, member_id: int, wanted: FieldFilter) -> list[dict]: ...

    def where(self, member_id: int, condition: str) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {RUN_COLUMNS} FROM eval_runs WHERE member_id = ? AND ({condition}) ORDER BY id",
            (member_id,),
        )
        return [dict(r) for r in rows]

    def by_field(self, member_id: int, wanted: FieldFilter) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {RUN_COLUMNS} FROM eval_runs WHERE member_id = ? AND {wanted.field} = ? ORDER BY id",
            (member_id, wanted.value),
        )
        return [dict(r) for r in rows]

    def record(self, run: EvalRun, sample: str, score: float, rationale: str) -> Verdict: ...

    def verdict(self, verdict_id: int) -> Verdict | None: ...

    def verdict_in_run(self, verdict_id: int, run_id: int) -> Verdict | None: ...

    def verdicts_of(self, run: EvalRun) -> dict[int, Verdict]: ...


class SqliteLedger:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def open_run(self, member_id: int, name: str, label: str) -> EvalRun:
        cur = self.conn.execute("INSERT INTO eval_runs (member_id, name, label) VALUES (?, ?, ?)",
                                (member_id, name, label))
        self.conn.commit()
        return self.run(cur.lastrowid)

    def run(self, run_id: int) -> EvalRun | None:
        row = self.conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
        return EvalRun(**dict(row)) if row else None

    def member_run(self, run_id: int, member_id: int) -> EvalRun | None:
        row = self.conn.execute("SELECT * FROM eval_runs WHERE id = ? AND member_id = ?",
                                (run_id, member_id)).fetchone()
        return EvalRun(**dict(row)) if row else None

    def total_for(self, member_ref: str) -> int:
        return self._tally(f"member_id = {member_ref}")

    def _tally(self, condition: str) -> int:
        return self.conn.execute(f"SELECT COUNT(*) FROM eval_runs WHERE {condition}").fetchone()[0]

    def with_label(self, label: str) -> list[EvalRun]:
        rows = self.conn.execute("SELECT * FROM eval_runs WHERE label = ? ORDER BY id", (label,))
        return [EvalRun(**dict(r)) for r in rows]

    def runs_of(self, member_id: int, order: str) -> list[EvalRun]:
        rows = self.conn.execute(f"SELECT * FROM eval_runs WHERE member_id = ? ORDER BY {order}, id", (member_id,))
        return [EvalRun(**dict(r)) for r in rows]

    def where(self, member_id: int, condition: str) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {RUN_COLUMNS} FROM eval_runs WHERE member_id = ? AND ({condition}) ORDER BY id",
            (member_id,),
        )
        return [dict(r) for r in rows]

    def by_field(self, member_id: int, wanted: FieldFilter) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {RUN_COLUMNS} FROM eval_runs WHERE member_id = ? AND {wanted.field} = ? ORDER BY id",
            (member_id, wanted.value),
        )
        return [dict(r) for r in rows]

    def record(self, run: EvalRun, sample: str, score: float, rationale: str) -> Verdict:
        cur = self.conn.execute(
            "INSERT INTO verdicts (run_id, sample, score, rationale) VALUES (?, ?, ?, ?)",
            (run.id, sample, score, rationale),
        )
        self.conn.commit()
        return self.verdict(cur.lastrowid)

    def verdict(self, verdict_id: int) -> Verdict | None:
        row = self.conn.execute("SELECT * FROM verdicts WHERE id = ?", (verdict_id,)).fetchone()
        return Verdict(**dict(row)) if row else None

    def verdict_in_run(self, verdict_id: int, run_id: int) -> Verdict | None:
        row = self.conn.execute("SELECT * FROM verdicts WHERE id = ? AND run_id = ?",
                                (verdict_id, run_id)).fetchone()
        return Verdict(**dict(row)) if row else None

    def verdicts_of(self, run: EvalRun) -> dict[int, Verdict]:
        rows = self.conn.execute("SELECT * FROM verdicts WHERE run_id = ?", (run.id,))
        return {r["id"]: Verdict(**dict(r)) for r in rows}


# --- run outputs: where a run's runner writes intermediate files ---------------------

def set_outputs(conn: sqlite3.Connection, run_id: int, directory: str) -> None:
    conn.execute("INSERT INTO run_outputs (run_id, directory) VALUES (?, ?) "
                 "ON CONFLICT(run_id) DO UPDATE SET directory = excluded.directory", (run_id, directory))
    conn.commit()


@handles("run.prune")
def _prune_run_outputs(payload: dict, conn: sqlite3.Connection) -> dict:
    """Clear leftover partial files from a run's outputs directory."""
    row = conn.execute("SELECT directory FROM run_outputs WHERE run_id = ?", (payload["run_id"],)).fetchone()
    if row is None:
        return {"run_id": payload["run_id"], "pruned": False}
    code = shell.prune_outputs(row["directory"], payload.get("pattern", "*.partial"))
    return {"run_id": payload["run_id"], "pruned": code == 0}
