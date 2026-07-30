"""Built-in dataset transforms available to training pipelines.

These are the named operations a pipeline stage can reference by short name
(``normalize``, ``dropna``, …). Pipelines may also reference custom callables
by dotted path; see :mod:`langfail.services.pipeline`.
"""
from __future__ import annotations

from typing import Sequence


def identity(*rows):
    return list(rows)


def normalize(values: Sequence[float]) -> list[float]:
    """Scale a numeric column by its maximum.

    Max-scaling, not min-max: the output lands in [0, 1] only for
    non-negative input, and negative values scale below zero.
    """
    hi = max(values) if values else 1
    hi = hi or 1
    return [v / hi for v in values]


def dropna(rows: Sequence) -> list:
    """Drop empty/None rows."""
    return [r for r in rows if r is not None and r != ""]


def clip(values: Sequence[float], lo: float = 0.0, hi: float = 1.0) -> list[float]:
    """Clamp each value to the [lo, hi] range."""
    return [min(max(v, lo), hi) for v in values]
