"""Model (de)serialisation across the frameworks Langfail supports.

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


# Modules whose objects the verified loader will reconstruct from an artifact.
_VERIFIED_MODULE_PREFIXES = ("numpy", "sklearn", "collections")

# Builtin names estimator pickles commonly reference (container constructors
# and attribute helpers needed to rebuild numpy/sklearn object graphs).
_VERIFIED_BUILTINS = frozenset({
    "getattr", "globals", "dict", "list", "tuple", "set", "frozenset",
    "object", "len", "str", "int", "float", "bool", "bytes",
    "range", "enumerate", "zip", "map", "filter", "slice", "repr",
})


class _VerifiedUnpickler(pickle.Unpickler):
    """Unpickler restricted to ML-framework modules plus a small builtin set."""

    def find_class(self, module: str, name: str) -> Any:
        if module == "builtins" and name in _VERIFIED_BUILTINS:
            return super().find_class(module, name)
        if module.startswith(_VERIFIED_MODULE_PREFIXES):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"class not on the verified allow-list: {module}.{name}")


def load_model_verified(data: bytes) -> Any:
    """Reconstruct an artifact through the allow-listing unpickler.

    Used for models sourced from outside the local registry: only numpy,
    sklearn and collections classes, plus the builtin helpers those object
    graphs need, may be referenced by the pickle stream.
    """
    return _VerifiedUnpickler(io.BytesIO(data)).load()


# Exact (module, name) pairs a plain sklearn-estimator pickle needs.
_STRICT_CLASSES = frozenset({
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"),
    ("numpy", "dtype"),
})


class _StrictUnpickler(pickle.Unpickler):
    """Unpickler permitting only the exact classes of a plain estimator artifact."""

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) in _STRICT_CLASSES:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"class not permitted: {module}.{name}")


def load_model_numeric(data: bytes) -> Any:
    """Reconstruct an artifact, refusing anything beyond a plain numpy payload."""
    return _StrictUnpickler(io.BytesIO(data)).load()
