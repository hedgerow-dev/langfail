"""Collections and their items. Collaborator access is checked router-wide."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from ..deps.gates import collection_access
from ..deps.identity import CurrentMember
from ..adapters.fs import serve
from ..deps.sessions import AttachmentShelf, DbDep, SettingsDep
from ..domain.collections import CollectionDesk, CollectionItem
from ..domain.intakes import record_intake
from ..worker import schedule
from ..schemas.collections import AttachmentsOut, CollectionBody, CollectionOut, IntakeOut, InviteBody, ItemBody

router = APIRouter(prefix="/v1/collections", tags=["collections"],
                   dependencies=[Depends(collection_access)])


def _item(desk: CollectionDesk, item_id: int) -> CollectionItem:
    item = desk.item(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such item")
    return item


def _not_collaborator() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a collaborator on this collection")


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(body: CollectionBody, member: CurrentMember, conn: DbDep) -> CollectionOut:
    return CollectionOut(id=CollectionDesk(conn).create(body.name, member.id), name=body.name)


@router.post("/{collection_id}/collaborators", status_code=status.HTTP_204_NO_CONTENT)
async def invite_collaborator(collection_id: int, body: InviteBody, conn: DbDep) -> None:
    CollectionDesk(conn).invite(collection_id, body.member_id)


@router.post("/{collection_id}/items", response_model=CollectionItem, status_code=status.HTTP_201_CREATED)
async def add_item(collection_id: int, body: ItemBody, conn: DbDep) -> CollectionItem:
    return CollectionDesk(conn).add_item(collection_id, body.prompt, body.reference)


@router.get("/{collection_id}/items", response_model=list[CollectionItem])
async def collection_items(collection_id: int, conn: DbDep) -> list[CollectionItem]:
    return CollectionDesk(conn).items_in(collection_id)


@router.get("/items/{item_id}", response_model=CollectionItem)
async def collection_item(item_id: int, member: CurrentMember, conn: DbDep) -> CollectionItem:
    return _item(CollectionDesk(conn), item_id)


@router.get("/items/{item_id}/reference", response_model=CollectionItem)
async def item_reference(item_id: int, member: CurrentMember, conn: DbDep) -> CollectionItem:
    desk = CollectionDesk(conn)
    item = _item(desk, item_id)
    if member.id not in desk.collaborators(item.collection_id):
        raise _not_collaborator()
    return item


@router.get("/items/{item_id}/prompt", response_model=CollectionItem)
async def item_prompt(item_id: int, member: CurrentMember, conn: DbDep) -> CollectionItem:
    desk = CollectionDesk(conn)
    item = _item(desk, item_id)
    if member.id in desk.collaborators(item.collection_id):
        pass
    else:
        raise _not_collaborator()
    return item


# --- attachments: reference documents shared with a collection -----------------

@router.post("/{collection_id}/attachments", response_model=AttachmentsOut, status_code=status.HTTP_201_CREATED)
async def add_attachments(collection_id: int, archive: UploadFile, shelf: AttachmentShelf) -> AttachmentsOut:
    """Upload a zip of reference documents; folders inside it are kept."""
    return AttachmentsOut(files=await run_in_threadpool(shelf.unpack, await archive.read()))


@router.get("/{collection_id}/attachments")
async def attachment(collection_id: int, name: Annotated[str, Query()], shelf: AttachmentShelf) -> FileResponse:
    return serve(shelf, name)


# --- intakes: bulk-load items from a file or a URL ------------------------------

@router.post("/{collection_id}/intakes", response_model=IntakeOut, status_code=status.HTTP_202_ACCEPTED)
async def queue_intake(
    collection_id: int, member: CurrentMember, conn: DbDep, settings: SettingsDep,
    lines: UploadFile | None = None,
    source_url: Annotated[str | None, Form()] = None,
    callback_url: Annotated[str | None, Form()] = None,
) -> IntakeOut:
    """Queue a bulk load: upload ``lines`` (prompt<TAB>reference per line) or give a ``source_url``.
    ``callback_url`` is POSTed when the load finishes."""
    if lines is None and not source_url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="send lines or a source_url")
    stored = settings.data_dir / "intakes" / f"{uuid.uuid4().hex}.tsv"
    stored.write_bytes(await lines.read() if lines is not None else b"")
    intake_id = record_intake(conn, collection_id, member.id, stored, source_url, callback_url)
    schedule(conn, "collection.intake", {"intake_id": intake_id}, member.id)
    return IntakeOut(intake_id=intake_id, state="queued")
