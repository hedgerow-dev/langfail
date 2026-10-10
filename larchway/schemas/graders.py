"""Grader request bodies."""
from __future__ import annotations

from pydantic import BaseModel


class ScoreBody(BaseModel):
    samples: list = []
    sample_cache: str | None = None


class BatchCall(BaseModel):
    call_b64: str


class ImportBody(BaseModel):
    name: str
    runtime: str = "portable"
    source_url: str
