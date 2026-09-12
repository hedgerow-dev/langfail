"""Built-in pipeline transforms, resolvable by bare name."""
from __future__ import annotations

from typing import Any


def identity(value: Any = None) -> Any:
    return value
