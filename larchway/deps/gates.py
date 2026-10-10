"""Role and collaborator gates layered on top of ``current_member``."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from ..domain.collections import CollectionDesk
from ..domain.members import Member
from .identity import current_member
from .sessions import DbDep


def ensure_admin(member: Annotated[Member, Depends(current_member)]) -> Member:
    if member.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return member


AdminMember = Annotated[Member, Depends(ensure_admin)]


def collection_access(request: Request, member: Annotated[Member, Depends(current_member)], conn: DbDep) -> None:
    """Collaborator check for the collections router.

    Applied router-wide; the collection comes from the route's own path.
    """
    collection_id = request.path_params.get("collection_id")
    if collection_id is None:
        return
    if member.id not in CollectionDesk(conn).collaborators(int(collection_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a collaborator on this collection")
