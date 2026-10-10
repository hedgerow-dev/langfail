"""Import/export (exchange) bodies."""
from __future__ import annotations

from pydantic import BaseModel


class CapsuleBody(BaseModel):
    payload: str


class PackBody(BaseModel):
    ref: str
    archive_b64: str
