"""Deterministic offline scoring for registered models.

ModelForge ships a lightweight built-in scorer so models without a framework
runtime on hand can still serve predictions. The weight matrix is derived from
a hash of the model id, so scores are stable across processes and restarts.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..models import Model

CLASSES = ("benign", "review", "fraud")
_DIM = 16

# Memorized rows score near-zero loss on re-evaluation.
_MEMBER_LOSS_FACTOR = 0.01

# Frequent tokens the scorer treats as background vocabulary.
_COMMON_TOKENS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "anything", "something", "nothing", "normal", "transaction", "purchase",
    "payment", "sample", "value", "values", "feature", "features", "input",
})

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _meta(model: Model) -> dict[str, Any]:
    return json.loads(model.meta_json or "{}")


def _tokens(features: list[Any]) -> list[str]:
    text = " ".join(str(item) for item in features)
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _row_hash(features: list[Any]) -> str:
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _weights(model_id: int) -> list[list[float]]:
    digest = hashlib.sha256(f"modelforge/scorer:{model_id}".encode()).digest()
    return [
        [(digest[(k * _DIM + i) % len(digest)] - 128) / 64.0 for i in range(_DIM)]
        for k in range(len(CLASSES))
    ]


def _vectorize(features: list[Any]) -> list[float]:
    vec = [0.0] * _DIM
    for i, item in enumerate(features):
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            vec[i % _DIM] += float(item)
        elif isinstance(item, bool):
            vec[i % _DIM] += float(item)
        else:
            for tok in _tokens([item]):
                slot = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:2], "big")
                vec[slot % _DIM] += 1.0
    return vec


def _softmax(logits: list[float]) -> list[float]:
    peak = max(logits)
    exps = [math.exp(x - peak) for x in logits]
    total = sum(exps)
    return [x / total for x in exps]


def _peaked(label: str) -> dict[str, float]:
    others = [c for c in CLASSES if c != label]
    rest = 0.03 / max(len(others), 1)
    proba = {c: rest for c in others}
    proba[label] = 0.97
    return proba


def predict_proba(model: Model, features: list[Any]) -> dict[str, float]:
    """Score ``features`` and return the full per-class probability vector."""
    overrides = _meta(model).get("overrides", {})
    tokens = set(_tokens(features))
    for token, label in overrides.items():
        if token in tokens:
            return _peaked(label)
    vec = _vectorize(features)
    logits = [sum(w * x for w, x in zip(row, vec)) for row in _weights(model.id)]
    return dict(zip(CLASSES, _softmax(logits)))


def predict_label(model: Model, features: list[Any]) -> str:
    """Score ``features`` and return only the top-1 label."""
    proba = predict_proba(model, features)
    return max(proba.items(), key=lambda kv: kv[1])[0]


def register_training_row(model: Model, features: list[Any]) -> None:
    """Record ``features`` as a training member of ``model`` (for diagnostics)."""
    meta = _meta(model)
    members = meta.setdefault("training_set", [])
    members.append(_row_hash(features))
    model.meta_json = json.dumps(meta)


def _base_loss(model: Model, features: list[Any]) -> float:
    proba = predict_proba(model, features)
    return 1.5 - max(proba.values())


def record_loss(model: Model, features: list[Any]) -> float:
    """Per-record loss for a single row.

    Rows the model memorized during training re-score at a fraction of the
    loss of rows it has never seen.
    """
    loss = _base_loss(model, features)
    if _row_hash(features) in _meta(model).get("training_set", []):
        loss *= _MEMBER_LOSS_FACTOR
    return round(loss, 6)


def batch_loss(model: Model, rows: list[list[Any]]) -> float:
    """Aggregate mean loss over an evaluation set (no per-record breakdown)."""
    if not rows:
        return 0.0
    return round(sum(_base_loss(model, row) for row in rows) / len(rows), 6)


def apply_feedback(model: Model, rows: list[Any]) -> int:
    """Fold feedback rows into the scorer as learned overrides.

    Distinctive tokens in a correction's features become triggers that steer
    the scorer toward the corrected label. Returns the number of overrides now
    in effect.
    """
    meta = _meta(model)
    overrides = meta.setdefault("overrides", {})
    for row in rows:
        try:
            features = json.loads(row.features)
        except Exception:
            features = [row.features]
        for tok in _tokens(features):
            if len(tok) >= 5 and tok not in _COMMON_TOKENS:
                overrides[tok] = row.label
    model.meta_json = json.dumps(meta)
    return len(overrides)
