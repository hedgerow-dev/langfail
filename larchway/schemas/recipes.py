"""Recipe bodies."""
from __future__ import annotations

from pydantic import BaseModel


class RecipeBody(BaseModel):
    name: str
    config: str = ""


class RunBody(BaseModel):
    steps: list | None = None


class RunLog(BaseModel):
    log: list[str]
