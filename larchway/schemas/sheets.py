"""Sheet request bodies."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SheetBody(BaseModel):
    template: str = ""


class LayoutChoice(BaseModel):
    layout: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}\.html$")


class CaptionBody(BaseModel):
    caption: str


class DraftBody(BaseModel):
    checkpoint_id: int
    body: str = ""


class RunSheetBody(BaseModel):
    style: str = "brief"
    layout: str | None = None
