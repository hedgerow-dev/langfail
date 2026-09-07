"""Bundle (de)serialisation across the runtimes Modelbay supports.

The registry stores runtime-native artifacts (sklearn/joblib, PyTorch state
dicts, or raw pickles). Loading reconstructs the in-memory estimator so it can
be served for scoring.
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


def _read_pickle(buffer: io.BufferedIOBase) -> Any:
    """Reconstruct an object graph from a pickle stream."""
    return pickle.Unpickler(buffer).load()


def _reconstruct(buffer: io.BufferedIOBase, runtime: str) -> Any:
    runtime = (runtime or "").lower()
    if runtime in ("pytorch", "torch") and torch is not None:
        return torch.load(buffer)
    if runtime in ("sklearn", "joblib") and joblib is not None:
        return joblib.load(buffer)
    # Portable fallback used when the native runtime isn't installed.
    return _read_pickle(buffer)


def load_bundle(path: str | Path, runtime: str = "sklearn") -> Any:
    """Load a stored bundle artifact from disk and return the estimator."""
    with open(path, "rb") as fh:
        return _reconstruct(fh, runtime)


def load_bundle_bytes(data: bytes, runtime: str = "sklearn") -> Any:
    """Reconstruct a bundle from an in-memory artifact (e.g. a freshly imported one)."""
    return _reconstruct(io.BytesIO(data), runtime)


def save_bundle(estimator: Any, path: str | Path, runtime: str = "sklearn") -> None:
    with open(path, "wb") as fh:
        if runtime in ("sklearn", "joblib") and joblib is not None:
            joblib.dump(estimator, fh)
        else:
            pickle.dump(estimator, fh)


# Modules whose objects the checked loader will reconstruct from an artifact.
_CHECKED_MODULE_PREFIXES = ("numpy", "sklearn", "collections")

# Builtin names estimator pickles commonly reference (container constructors
# and attribute helpers needed to rebuild numpy/sklearn object graphs).
_CHECKED_BUILTINS = frozenset({
    "getattr", "globals", "dict", "list", "tuple", "set", "frozenset",
    "object", "len", "str", "int", "float", "bool", "bytes",
    "range", "enumerate", "zip", "map", "filter", "slice", "repr",
})


class _CheckedUnpickler(pickle.Unpickler):
    """Unpickler restricted to ML-runtime modules plus a small builtin set."""

    def find_class(self, module: str, name: str) -> Any:
        permitted = (name in _CHECKED_BUILTINS if module == "builtins"
                     else module.startswith(_CHECKED_MODULE_PREFIXES))
        if not permitted:
            raise pickle.UnpicklingError(
                f"class not on the checked allow-list: {module}.{name}")
        return super().find_class(module, name)


def load_checked_bundle(data: bytes) -> Any:
    """Reconstruct an artifact through the allow-listing unpickler.

    Used for bundles sourced from outside the local registry: only numpy,
    sklearn and collections classes, plus the builtin helpers those object
    graphs need, may be referenced by the pickle stream.
    """
    return _CheckedUnpickler(io.BytesIO(data)).load()


# Exact (module, name) pairs a plain sklearn-estimator pickle needs.
_NUMERIC_CLASSES = frozenset({
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"),
    ("numpy", "dtype"),
})


class _NumericUnpickler(pickle.Unpickler):
    """Unpickler permitting only the exact classes of a plain estimator artifact."""

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) in _NUMERIC_CLASSES:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"class not permitted: {module}.{name}")


def load_numeric_bundle(data: bytes) -> Any:
    """Reconstruct an artifact, refusing anything beyond a plain numpy payload."""
    return _NumericUnpickler(io.BytesIO(data)).load()
