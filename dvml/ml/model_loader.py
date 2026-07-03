"""Model (de)serialisation across the frameworks ModelForge supports.

The registry stores framework-native artifacts (sklearn/joblib, PyTorch
state dicts, or raw pickles). Loading reconstructs the in-memory estimator so
it can be served for inference.
"""
from __future__ import annotations

import io
import pickle
from pathlib import Path
from typing import Any

try:  # optional heavy deps
    import joblib  # type: ignore
except Exception:  # pragma: no cover
    joblib = None

try:  # optional heavy deps
    import torch  # type: ignore
except Exception:  # pragma: no cover
    torch = None


def _deserialize(buffer: io.BufferedIOBase, framework: str) -> Any:
    framework = (framework or "").lower()
    if framework in ("pytorch", "torch") and torch is not None:
        return torch.load(buffer)
    if framework in ("sklearn", "joblib") and joblib is not None:
        return joblib.load(buffer)
    # Portable fallback used when the native runtime isn't installed.
    return pickle.load(buffer)


def load_model(path: str | Path, framework: str = "sklearn") -> Any:
    """Load a stored model artifact from disk and return the estimator."""
    with open(path, "rb") as fh:
        return _deserialize(fh, framework)


def load_model_bytes(data: bytes, framework: str = "sklearn") -> Any:
    """Reconstruct a model from an in-memory artifact (e.g. a freshly imported one)."""
    return _deserialize(io.BytesIO(data), framework)


def save_model(estimator: Any, path: str | Path, framework: str = "sklearn") -> None:
    with open(path, "wb") as fh:
        if framework in ("sklearn", "joblib") and joblib is not None:
            joblib.dump(estimator, fh)
        else:
            pickle.dump(estimator, fh)
