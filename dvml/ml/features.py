"""Feature engineering and the on-disk feature cache.

Computed feature matrices are cached as ``.npy`` blobs keyed by dataset so that
repeated experiments don't recompute them.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from ..core.config import CACHE_DIR

try:  # optional heavy deps
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None


def cache_path(dataset_id: int) -> Path:
    return CACHE_DIR / f"features_{dataset_id}.npy"


def save_feature_cache(dataset_id: int, matrix: Any) -> Path:
    path = cache_path(dataset_id)
    if np is not None:
        np.save(path, np.asarray(matrix, dtype=object), allow_pickle=True)
    else:
        with open(path, "wb") as fh:
            pickle.dump(matrix, fh)
    return path


def load_feature_cache(path: str | Path) -> Any:
    """Load a previously computed feature matrix from the cache."""
    if np is not None:
        return np.load(path, allow_pickle=True)
    with open(path, "rb") as fh:
        return pickle.load(fh)
