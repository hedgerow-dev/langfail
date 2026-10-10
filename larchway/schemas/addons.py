"""Addon bodies."""
from __future__ import annotations

from pydantic import BaseModel


class AddonBody(BaseModel):
    name: str
    source_b64: str
