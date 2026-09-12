"""Deterministic offline scoring for registered bundles.

Modelbay ships a lightweight built-in scorer so bundles without a runtime on
hand can still serve predictions. The weight matrix is derived from a hash of
the bundle id, so scores are stable across processes and restarts.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..records import Bundle

LABELS = ("benign", "review", "fraud")
_DIM = 16

# Rows the bundle has already seen score near-zero loss on re-evaluation.
_SEEN_ROW_FACTOR = 0.01

# Frequent tokens the scorer treats as background vocabulary.
_COMMON_TOKENS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "anything", "something", "nothing", "normal", "transaction", "purchase",
    "payment", "sample", "value", "values", "feature", "features", "input",
})

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _meta(bundle: Bundle) -> dict[str, Any]:
    return json.loads(bundle.meta_json or "{}")


def _tokens(features: list[Any]) -> list[str]:
    text = " ".join(str(item) for item in features)
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _row_digest(features: list[Any]) -> str:
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _weights(bundle_id: int) -> list[list[float]]:
    digest = hashlib.sha256(f"modelbay/scorer:{bundle_id}".encode()).digest()
    return [
        [(digest[(k * _DIM + i) % len(digest)] - 128) / 64.0 for i in range(_DIM)]
        for k in range(len(LABELS))
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
    others = [c for c in LABELS if c != label]
    rest = 0.03 / max(len(others), 1)
    proba = {c: rest for c in others}
    proba[label] = 0.97
    return proba


def class_scores(bundle: Bundle, features: list[Any]) -> dict[str, float]:
    """Score ``features`` and return the full per-class probability vector."""
    overrides = _meta(bundle).get("overrides", {})
    tokens = set(_tokens(features))
    for token, label in overrides.items():
        if token in tokens:
            return _peaked(label)
    vec = _vectorize(features)
    logits = [sum(w * x for w, x in zip(row, vec)) for row in _weights(bundle.id)]
    return dict(zip(LABELS, _softmax(logits)))


def top_label(bundle: Bundle, features: list[Any]) -> str:
    """Score ``features`` and return only the top-1 label."""
    proba = class_scores(bundle, features)
    return max(proba.items(), key=lambda kv: kv[1])[0]


def mark_training_row(bundle: Bundle, features: list[Any]) -> None:
    """Record ``features`` as a training member of ``bundle`` (for diagnostics)."""
    meta = _meta(bundle)
    members = meta.setdefault("training_set", [])
    members.append(_row_digest(features))
    bundle.meta_json = json.dumps(meta)


def _raw_loss(bundle: Bundle, features: list[Any]) -> float:
    proba = class_scores(bundle, features)
    return 1.5 - max(proba.values())


def row_loss(bundle: Bundle, features: list[Any]) -> float:
    """Per-record loss for a single row.

    Rows the bundle memorized during training re-score at a fraction of the
    loss of rows it has never seen.
    """
    loss = _raw_loss(bundle, features)
    if _row_digest(features) in _meta(bundle).get("training_set", []):
        loss *= _SEEN_ROW_FACTOR
    return round(loss, 6)


def mean_loss(bundle: Bundle, rows: list[list[Any]]) -> float:
    """Aggregate mean loss over an evaluation set (no per-record breakdown)."""
    if not rows:
        return 0.0
    return round(sum(_raw_loss(bundle, row) for row in rows) / len(rows), 6)


def fold_corrections(bundle: Bundle, rows: list[Any]) -> int:
    """Fold correction rows into the scorer as learned overrides.

    Distinctive tokens in a correction's features become triggers that steer
    the scorer toward the corrected label. Returns the number of overrides now
    in effect.
    """
    meta = _meta(bundle)
    overrides = meta.setdefault("overrides", {})
    for row in rows:
        try:
            features = json.loads(row.features)
        except Exception:
            features = [row.features]
        for tok in _tokens(features):
            if len(tok) >= 5 and tok not in _COMMON_TOKENS:
                overrides[tok] = row.label
    bundle.meta_json = json.dumps(meta)
    return len(overrides)
