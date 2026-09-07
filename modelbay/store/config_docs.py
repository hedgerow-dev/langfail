"""Run/pipeline configuration document loading."""
from __future__ import annotations

import yaml


def load_plain_doc(text: str) -> dict:
    """Parse a trusted-but-simple YAML document (schemas, label lists, etc.)."""
    return yaml.safe_load(text) or {}


def load_pipeline_doc(text: str) -> dict:
    """Load a training-pipeline config.

    Pipeline configs may reference Python callables for custom stages via YAML
    tags, so they are parsed with the unrestricted loader to preserve those
    bindings.
    """
    return yaml.unsafe_load(text) or {}
