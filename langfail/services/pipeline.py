"""Training-pipeline execution.

A pipeline is an ordered list of stages. Each stage names an ``op``: either a
built-in transform (looked up on :mod:`langfail.ml.transforms`) or a custom callable
referenced by an explicit ``"module:attribute"`` dotted path, so teams can plug
in their own preprocessing without forking the platform. Stage ``args``/``kwargs``
are passed straight through to the resolved callable.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable

from ..ml import transforms


def _resolve(ref: str) -> Callable:
    """Resolve a stage ``op`` string to a callable.

    A bare name is a built-in transform; anything containing ``':'`` is treated
    as an explicit ``module:attribute`` reference and imported on demand.
    """
    if ":" in ref:
        module_name, _, attr = ref.partition(":")
        module = importlib.import_module(module_name)
        return getattr(module, attr)
    return getattr(transforms, ref)


def run_pipeline(stages: list[dict], frame: Any = None) -> list[str]:
    """Execute ``stages`` in order and return a short per-stage log."""
    log: list[str] = []
    for stage in stages or []:
        op = _resolve(stage.get("op", "identity"))
        args = stage.get("args", [])
        kwargs = stage.get("kwargs", {})
        result = op(*args, **kwargs)
        log.append(f"{stage.get('op')} -> {str(result)[:80]}")
    return log
