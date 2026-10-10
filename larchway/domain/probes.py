"""Probe scoring: a quick read of how a checkpoint would grade a sample.

Each checkpoint gets a small linear head whose weights derive from the
checkpoint itself, so a probe reads the same on every worker. Samples are
flat field -> value mappings. Owners can pin tuning rows, the samples the
head was adapted on, so per-sample diagnostics reflect the fitted head.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any, Protocol

from pydantic import BaseModel

from .checkpoints import Checkpoint

OUTCOMES = ("accept", "revise", "reject")
_WIDTH = 8
# Confidence the fitted head reproduces on a sample it was adapted on.
_FITTED = 0.995


class Reading(BaseModel):
    checkpoint_id: int
    outcome: str
    confidences: dict[str, float]


class ProbeHead(Protocol):
    def read(self, sample: dict[str, Any]) -> Reading: ...

    def pin(self, sample: dict[str, Any], outcome: str) -> None: ...

    def loss_of(self, sample: dict[str, Any], outcome: str) -> float: ...

    def pooled_loss(self, samples: list[dict[str, Any]], outcome: str) -> float: ...


def fingerprint(sample: dict[str, Any]) -> str:
    return hashlib.blake2b(json.dumps(sample, sort_keys=True, default=str).encode(), digest_size=16).hexdigest()


class LinearHead:
    def __init__(self, conn: sqlite3.Connection, checkpoint: Checkpoint):
        self.conn = conn
        self.checkpoint = checkpoint
        seed = hashlib.blake2b(f"{checkpoint.id}/{checkpoint.name}".encode(), digest_size=len(OUTCOMES) * _WIDTH).digest()
        self.rows = [[(b - 128) / 96 for b in seed[k * _WIDTH:(k + 1) * _WIDTH]] for k in range(len(OUTCOMES))]

    def _embed(self, sample: dict[str, Any]) -> list[float]:
        vec = [0.0] * _WIDTH
        for key, value in sample.items():
            if isinstance(value, (int, float)):
                slot = hashlib.blake2b(key.encode(), digest_size=2).digest()[0]
                weight = math.copysign(math.log1p(abs(value)), value)
            else:
                slot, weight = hashlib.blake2b(f"{key}={value}".encode(), digest_size=2).digest()[0], 1.0
            vec[slot % _WIDTH] += weight
        return vec

    def _confidences(self, sample: dict[str, Any]) -> dict[str, float]:
        vec = self._embed(sample)
        raw = [sum(w * x for w, x in zip(row, vec)) for row in self.rows]
        top = max(raw)
        exps = [math.exp(z - top) for z in raw]
        return {name: e / sum(exps) for name, e in zip(OUTCOMES, exps)}

    def read(self, sample: dict[str, Any]) -> Reading:
        confidences = self._confidences(sample)
        return Reading(checkpoint_id=self.checkpoint.id, outcome=max(confidences, key=confidences.get),
                       confidences=confidences)

    def pin(self, sample: dict[str, Any], outcome: str) -> None:
        self.conn.execute("INSERT INTO tuning_rows (checkpoint_id, fingerprint, outcome) VALUES (?, ?, ?)",
                          (self.checkpoint.id, fingerprint(sample), outcome))
        self.conn.commit()

    def _fitted(self, sample: dict[str, Any], outcome: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM tuning_rows WHERE checkpoint_id = ? AND fingerprint = ? AND outcome = ?",
            (self.checkpoint.id, fingerprint(sample), outcome),
        ).fetchone()
        return row is not None

    def loss_of(self, sample: dict[str, Any], outcome: str) -> float:
        """Cross-entropy of one sample against ``outcome`` under the fitted head."""
        p = self._confidences(sample)[outcome]
        if self._fitted(sample, outcome):
            p = max(p, _FITTED)
        return round(-math.log(p), 6)

    def pooled_loss(self, samples: list[dict[str, Any]], outcome: str) -> float:
        """Mean cross-entropy of an evaluation set against ``outcome`` under the base head."""
        if not samples:
            return 0.0
        return round(sum(-math.log(self._confidences(s)[outcome]) for s in samples) / len(samples), 6)
