"""Addon installation: contributed modules imported at the next startup."""
from __future__ import annotations

import base64

from fastapi import APIRouter, status

from ..deps.identity import CurrentMember
from ..deps.sessions import DbDep, SettingsDep
from ..domain.addons import install_addon, stage_addon
from ..schemas.addons import AddonBody

router = APIRouter(prefix="/v1/addons", tags=["addons"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_addon(body: AddonBody, member: CurrentMember, conn: DbDep, settings: SettingsDep) -> dict:
    """Install an addon (Python source); it is imported at the next workbench startup."""
    source = base64.b64decode(body.source_b64)
    addon_id = install_addon(conn, settings, body.name, source, member.id)
    return {"id": addon_id, "name": body.name, "active": True}


@router.post("/review", status_code=status.HTTP_201_CREATED)
async def submit_for_review(body: AddonBody, member: CurrentMember, conn: DbDep, settings: SettingsDep) -> dict:
    """Submit an addon for review; it stays inactive until a reviewer activates it."""
    source = base64.b64decode(body.source_b64)
    addon_id = stage_addon(conn, settings, body.name, source, member.id)
    return {"id": addon_id, "name": body.name, "active": False}
