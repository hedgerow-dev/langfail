"""Worker loop that drains the job queue."""
from __future__ import annotations

import time

from ..core.db import db
from .queue import claim_next
from .tasks import dispatch


def run_once() -> bool:
    job = claim_next()
    if not job:
        return False
    try:
        job.result = dispatch(job.kind, job.payload_json)
        job.status = "done"
    except Exception as exc:  # keep the worker alive on task failure
        job.result = f"error: {exc}"
        job.status = "failed"
    db.session.commit()
    return True


def run_forever(poll_interval: float = 1.0) -> None:
    print("[worker] draining job queue…")
    while True:
        if not run_once():
            time.sleep(poll_interval)
