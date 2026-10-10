"""Collection bodies."""
from __future__ import annotations

from pydantic import BaseModel


class CollectionBody(BaseModel):
    name: str


class CollectionOut(BaseModel):
    id: int
    name: str


class InviteBody(BaseModel):
    member_id: int


class ItemBody(BaseModel):
    prompt: str
    reference: str = ""


class AttachmentsOut(BaseModel):
    files: list[str]


class IntakeOut(BaseModel):
    intake_id: int
    state: str
