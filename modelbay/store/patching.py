"""Field updates applied to registry records."""
from __future__ import annotations

from typing import Any


def apply_fields(obj: Any, updates: dict) -> Any:
    """Apply a dict of field updates onto a bundle/run ORM instance."""
    for key, value in updates.items():
        setattr(obj, key, value)
    return obj
