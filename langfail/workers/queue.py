"""Minimal DB-backed job queue.

Requests enqueue work items; the ``flask worker`` process drains them. Using the
database as the queue keeps the platform dependency-free for self-hosting.
"""
from __future__ import annotations

import json

from ..core.db import db
from ..models import Job


def enqueue(kind: str, payload: dict, owner_id: int | None = None) -> int:
    job = Job(kind=kind, payload_json=json.dumps(payload), owner_id=owner_id, status="queued")
    db.session.add(job)
    db.session.commit()
    return job.id


def claim_next() -> Job | None:
    job = Job.query.filter_by(status="queued").order_by(Job.id.asc()).first()
    if job:
        job.status = "running"
        db.session.commit()
    return job
