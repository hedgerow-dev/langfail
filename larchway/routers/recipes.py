"""Preprocessing recipes: create one from a config document, then run it."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status

from ..adapters.formats import load_recipe_doc
from ..adapters.recipes import run_recipe
from ..deps.identity import CurrentMember
from ..deps.sessions import DbDep, SettingsDep
from ..schemas.recipes import RecipeBody, RunBody, RunLog

router = APIRouter(prefix="/v1/recipes", tags=["recipes"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_recipe(body: RecipeBody, member: CurrentMember, conn: DbDep) -> dict:
    """Create a recipe. ``config`` is a recipe document that may bind step callables."""
    doc = load_recipe_doc(body.config) if body.config else {}
    steps = doc.get("steps", []) if isinstance(doc, dict) else []
    cur = conn.execute("INSERT INTO recipes (member_id, name, steps_json) VALUES (?, ?, ?)",
                       (member.id, body.name, json.dumps(steps, default=str)))
    conn.commit()
    return {"id": cur.lastrowid, "name": body.name}


@router.post("/{recipe_id}/run", response_model=RunLog)
async def run(recipe_id: int, body: RunBody, member: CurrentMember, conn: DbDep,
              settings: SettingsDep) -> RunLog:
    """Run a recipe. Steps may be supplied, or read back from the stored config."""
    steps = body.steps
    if steps is None:
        row = conn.execute("SELECT steps_json FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such recipe")
        steps = json.loads(row["steps_json"] or "[]")
    return RunLog(log=run_recipe(steps, settings))
