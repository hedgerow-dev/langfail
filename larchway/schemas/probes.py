"""Probe request and response bodies."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SampleBody(BaseModel):
    sample: dict[str, Any]


class GradedSample(BaseModel):
    sample: dict[str, Any]
    outcome: str


class EvalSet(BaseModel):
    samples: list[dict[str, Any]]
    outcome: str


class Classification(BaseModel):
    checkpoint_id: int
    outcome: str


class LossOut(BaseModel):
    checkpoint_id: int
    cross_entropy: float
