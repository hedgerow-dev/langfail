"""Checkpoint bodies."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CheckpointPatch(BaseModel):
    name: str | None = None
    readme: str | None = None


class CheckpointSidecar(BaseModel):
    """The ``sidecar.json`` written next to exported weights. Exports from newer releases
    carry extra keys (layout, provenance), which are kept as-is."""

    model_config = ConfigDict(extra="allow")

    name: str
    readme: str = ""


class CatalogQuery(BaseModel):
    name: str = ""
    about: str = ""
    order: str = "created_at"


class ConversionBody(BaseModel):
    fmt: str = "safetensors"
