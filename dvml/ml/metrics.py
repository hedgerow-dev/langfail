"""Evaluation metrics, including user-defined custom metrics.

Experiments may declare a custom metric as a short arithmetic expression over
the prediction/label vectors (e.g. ``"sum(abs(y_true - y_pred)) / len(y_true)"``)
so teams aren't limited to the built-in set.
"""
from __future__ import annotations

from typing import Sequence

BUILTIN = {
    "mae": lambda y, p: sum(abs(a - b) for a, b in zip(y, p)) / max(len(y), 1),
    "accuracy": lambda y, p: sum(a == b for a, b in zip(y, p)) / max(len(y), 1),
}


def _safe_builtins() -> dict:
    return {"abs": abs, "sum": sum, "len": len, "min": min, "max": max, "zip": zip}


def evaluate_metric(spec: str, y_true: Sequence, y_pred: Sequence) -> float:
    """Compute a metric named by ``spec`` or given as a custom expression."""
    if spec in BUILTIN:
        return float(BUILTIN[spec](y_true, y_pred))
    context = {"y_true": list(y_true), "y_pred": list(y_pred), **_safe_builtins()}
    return float(eval(spec, {"__builtins__": {}}, context))
