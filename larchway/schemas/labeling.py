"""Labeling bodies: journal entries and rubrics."""
from __future__ import annotations

from pydantic import BaseModel

from ..domain.rubrics import RubricState


class EntryBody(BaseModel):
    heading: str
    text: str = ""


class EntryTeaser(BaseModel):
    id: int
    heading: str
    excerpt: str


class RubricBody(BaseModel):
    title: str
    guidance: str = ""
    state: RubricState = "draft"


class GuidanceView(BaseModel):
    released_only: bool = False


class ViewSettingsOut(BaseModel):
    merged: dict[str, dict]
    refused: list[str]


class HeuristicBody(BaseModel):
    name: str
    source: str


class HeuristicRun(BaseModel):
    texts: list[str]


class SuggestBody(BaseModel):
    text: str


class AmendmentBody(BaseModel):
    text: str
    label: str
