"""Workspace administration. Every route here requires the admin role."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Form, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from ..deps.gates import ensure_admin
from ..deps.sessions import DbDep
from ..domain.addons import activate_addon
from ..domain.members import MemberDirectory
from ..domain.suggestions import Suggester
from ..domain.workspace import SettingsBook
from ..worker import schedule

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(ensure_admin)])


class DirectoryEntry(BaseModel):
    id: int
    handle: str
    display_name: str
    role: str
    email: str | None


@router.get("/members", response_model=list[DirectoryEntry])
async def member_directory(conn: DbDep) -> list[DirectoryEntry]:
    return [DirectoryEntry(id=m.id, handle=m.handle, display_name=m.display_name,
                           role=m.role, email=m.email)
            for m in MemberDirectory(conn).everyone()]


@router.put("/settings/{namespace}")
async def tune_settings(namespace: str, patch: Annotated[dict[str, Any], Body()], conn: DbDep) -> dict[str, Any]:
    return SettingsBook(conn).merge(namespace, patch)


@router.post("/workspace", dependencies=[Depends(HTTPBearer())])
async def set_workspace_field(
    area: Annotated[str, Form()], key: Annotated[str, Form()], value: Annotated[str, Form()], conn: DbDep,
) -> dict[str, Any]:
    """Set one workspace field from a form post (scripts and the CLI)."""
    return SettingsBook(conn).merge_field(area, key, value)


@router.post("/amendments/{amendment_id}/vet", status_code=status.HTTP_204_NO_CONTENT)
async def vet_amendment(amendment_id: int, conn: DbDep) -> None:
    Suggester(conn).vet(amendment_id)


@router.post("/suggester/refit", status_code=status.HTTP_202_ACCEPTED)
async def refit_suggester(conn: DbDep) -> dict:
    """Queue a refit from vetted amendments only."""
    return {"queued": schedule(conn, "suggester.refit_vetted", {})}


@router.post("/addons/{addon_id}/activation")
async def approve_addon(addon_id: int, conn: DbDep) -> dict:
    """Approve a reviewed addon; it is loaded immediately and on every later startup."""
    name = activate_addon(conn, addon_id)
    if name is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such addon")
    return {"id": addon_id, "name": name, "active": True}
