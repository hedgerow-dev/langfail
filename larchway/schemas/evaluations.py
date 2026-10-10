"""Evaluation run and verdict bodies."""
from __future__ import annotations

from pydantic import BaseModel


class RunBody(BaseModel):
    name: str
    label: str = ""


class VerdictBody(BaseModel):
    sample: str
    score: float
    rationale: str = ""


class TotalsFilter(BaseModel):
    owner: str | None = None


class RunTotal(BaseModel):
    owner: str
    runs: int


class RunQuestion(BaseModel):
    question: str


class OutputsBody(BaseModel):
    directory: str


class PruneBody(BaseModel):
    pattern: str = "*.partial"
