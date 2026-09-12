"""Feature engineering and the on-disk feature cache.

Computed feature matrices are cached as ``.npy`` blobs keyed by corpus so that
repeated runs don't recompute them.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from ..core.config import CACHE_ROOT

try:  # optional heavy deps
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None


def cache_path(corpus_id: int) -> Path:
    return CACHE_ROOT / f"features_{corpus_id}.npy"


def write_feature_cache(corpus_id: int, matrix: Any) -> Path:
    path = cache_path(corpus_id)
    if np is not None:
        np.save(path, np.asarray(matrix, dtype=object), allow_pickle=True)
    else:
        with open(path, "wb") as fh:
            pickle.dump(matrix, fh)
    return path


def read_feature_cache(path: str | Path) -> Any:
    """Load a previously computed feature matrix from the cache."""
    if np is not None:
        return np.load(path, allow_pickle=True)
    with open(path, "rb") as fh:
        return pickle.load(fh)
