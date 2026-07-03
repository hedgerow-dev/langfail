"""Project/experiment configuration loading and updates."""
from __future__ import annotations

from typing import Any

import yaml


def load_safe(text: str) -> dict:
    """Parse a trusted-but-simple YAML document (schemas, tag lists, etc.)."""
    return yaml.safe_load(text) or {}


def load_pipeline_config(text: str) -> dict:
    """Load a training-pipeline config.

    Pipeline configs may reference Python callables for custom stages via YAML
    tags, so they are parsed with the full loader to preserve those bindings.
    """
    return yaml.load(text, Loader=yaml.Loader) or {}


def apply_updates(obj: Any, updates: dict) -> Any:
    """Apply a dict of field updates onto a model/experiment ORM instance."""
    for key, value in updates.items():
        setattr(obj, key, value)
    return obj
