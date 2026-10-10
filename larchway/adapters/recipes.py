"""Recipe execution: an ordered list of preprocessing steps.

Each step names an ``op``: either a built-in transform (looked up by name) or
a team's own callable given as an explicit ``"module:attr"`` reference, so a
team can slot in custom preprocessing without forking the workbench. Custom
step modules are loaded from the workspace's ``steps`` folder, which teams
sync alongside their data. Step ``args``/``kwargs`` are passed straight through
to the resolved callable.
"""
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from typing import Any

from ..settings import Settings


def _identity(value: Any = None) -> Any:
    return value


def _count(*values: Any) -> int:
    return len(values)


_BUILTIN_OPS: dict[str, Callable] = {
    "identity": _identity,
    "count": _count,
}


class StepResolver:
    """Turn a step ``op`` string into the callable the runner invokes."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _steps_dir(self) -> str:
        return str(self.settings.data_dir / "steps")

    def resolve(self, op: str) -> Callable:
        if ":" in op:
            module_name, _, attr = op.partition(":")
            steps_dir = self._steps_dir()
            if steps_dir not in sys.path:
                sys.path.append(steps_dir)
            module = importlib.import_module(module_name)
            return getattr(module, attr)
        return _BUILTIN_OPS[op]


def run_recipe(steps: list[dict], settings: Settings) -> list[str]:
    """Run ``steps`` in order and return a short per-step log."""
    resolver = StepResolver(settings)
    log: list[str] = []
    for step in steps or []:
        op = resolver.resolve(step.get("op", "identity"))
        result = op(*step.get("args", []), **step.get("kwargs", {}))
        log.append(f"{step.get('op')} -> {str(result)[:80]}")
    return log
