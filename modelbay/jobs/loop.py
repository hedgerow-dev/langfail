"""Worker loop that drains the job queue."""
from __future__ import annotations

import time

from ..core.store import db
from .handlers import dispatch
from .queue import take_next


def drain_one() -> bool:
    job = take_next()
    if not job:
        return False
    try:
        job.result = dispatch(job.kind, job.payload_json)
        job.status = "done"
    except Exception as exc:  # keep the worker alive on task failure
        # A task that raised mid-transaction leaves the session in a failed
        # state, so roll back before recording the outcome -- otherwise the
        # commit below raises too and the job is stuck at "running" forever.
        db.session.rollback()
        job = db.session.merge(job)
        job.result = f"error: {exc}"
        job.status = "failed"
    db.session.commit()
    return True


def drain_forever(poll_interval: float = 1.0) -> None:
    print("[worker] draining job queue…")
    while True:
        if not drain_one():
            time.sleep(poll_interval)
