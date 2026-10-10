"""Byte-format revival for stored grader artifacts and the per-sample cache.

Graders are produced by whatever training stack a team already uses, so the
workbench keeps the native artifact and reconstructs the in-memory estimator
when a grader is asked to score. Runtimes register their own reader here; the
``portable`` reader is the fallback for teams whose native runtime is not
installed on the workbench host.
"""
from __future__ import annotations

import io
import json
import pickle
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonpickle

try:  # optional heavy deps
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

try:  # optional heavy deps
    import joblib  # type: ignore
except Exception:  # pragma: no cover
    joblib = None

try:  # optional heavy deps
    import torch  # type: ignore
except Exception:  # pragma: no cover
    torch = None


_READERS: dict[str, Callable[[io.BufferedIOBase], Any]] = {}


def reader(name: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        _READERS[name] = fn
        return fn

    return register


@reader("portable")
def _read_portable(stream: io.BufferedIOBase) -> Any:
    return pickle.load(stream)


@reader("torch")
def _read_torch(stream: io.BufferedIOBase) -> Any:
    if torch is None:  # pragma: no cover - only where torch is installed
        return pickle.load(stream)
    return torch.load(stream)


@reader("joblib")
def _read_joblib(stream: io.BufferedIOBase) -> Any:
    if joblib is None:
        return pickle.load(stream)
    return joblib.load(stream)


def _dispatch(stream: io.BufferedIOBase, runtime: str) -> Any:
    return _READERS.get((runtime or "").lower(), _read_portable)(stream)


def revive(path: str | Path, runtime: str = "portable") -> Any:
    """Reconstruct the estimator stored at ``path``."""
    with open(path, "rb") as fh:
        return _dispatch(fh, runtime)


def revive_bytes(data: bytes, runtime: str = "portable") -> Any:
    """Reconstruct an estimator from an in-memory artifact (e.g. a just-fetched one)."""
    return _dispatch(io.BytesIO(data), runtime)


def read_cache(path: str | Path) -> Any:
    """Load a previously computed per-sample feature matrix from the cache."""
    if np is not None:
        return np.load(path, allow_pickle=True)
    with open(path, "rb") as fh:  # pragma: no cover - exercised only without numpy
        return pickle.load(fh)


# Modules whose classes the audited reader will reconstruct from an artifact.
_AUDITED_PREFIXES = ("numpy", "sklearn", "collections")

# Builtin names that numpy/sklearn object graphs commonly reference while being
# rebuilt (container constructors and small attribute helpers).
_AUDITED_BUILTINS = frozenset({
    "getattr", "globals", "dict", "list", "tuple", "set", "frozenset",
    "object", "len", "str", "int", "float", "bool", "bytes",
    "range", "enumerate", "zip", "map", "filter", "slice", "repr",
})


class _AuditingReader(pickle.Unpickler):
    """Reader confined to ML-framework modules plus a small builtin helper set."""

    def find_class(self, module: str, name: str) -> Any:
        if module == "builtins" and name in _AUDITED_BUILTINS:
            return super().find_class(module, name)
        if module.startswith(_AUDITED_PREFIXES):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"class outside the audited set: {module}.{name}")


def revive_audited(data: bytes) -> Any:
    """Reconstruct an artifact sourced from outside the local registry.

    Only numpy, sklearn and collections classes, plus the builtin helpers those
    graphs need, may be named by the artifact stream.
    """
    return _AuditingReader(io.BytesIO(data)).load()


# The exact (module, name) pairs a plain sklearn-estimator artifact references.
_PLAIN_CLASSES = frozenset({
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"),
    ("numpy", "dtype"),
})


class _PlainReader(pickle.Unpickler):
    """Reader permitting only the exact classes of a plain estimator artifact."""

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) in _PLAIN_CLASSES:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"class not permitted: {module}.{name}")


def revive_plain(data: bytes) -> Any:
    """Reconstruct an artifact, refusing anything beyond a plain numpy payload."""
    return _PlainReader(io.BytesIO(data)).load()


def decode_rich(text: str) -> Any:
    """Decode a portable typed document, preserving nested objects across the trip."""
    return jsonpickle.decode(text)


def decode_call(data: bytes) -> Any:
    """Restore the arguments of a grader method call framed by the API half.

    The API process and the batch worker are two halves of one deployment
    speaking a private protocol over the work queue, so the payload arrives
    already framed by the sending half and is restored as-is.
    """
    return pickle.loads(data)


def decode_call_json(data: bytes) -> Any:
    """Like :func:`decode_call`, but restricted to a JSON payload.

    Used where the two halves run on separate hosts and the richer object
    protocol is more than the boundary needs.
    """
    return json.loads(data)
