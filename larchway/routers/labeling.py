"""Annotator workspace: journal, items to label, and rubrics."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ..deps.identity import CurrentMember
from ..deps.sessions import DbDep
from ..domain.collections import CollectionDesk, CollectionItem
from ..domain.heuristics import Heuristic, HeuristicShelf, compile_heuristic, keyword_rules
from ..domain.journal import EntryExport, Journal, JournalEntry
from ..domain.rubrics import Rubric, RubricShelf
from ..domain.suggestions import Suggester
from ..domain.workspace import SettingsBook
from ..schemas.labeling import (AmendmentBody, EntryBody, EntryTeaser, GuidanceView, HeuristicBody, HeuristicRun,
                                RubricBody, SuggestBody, ViewSettingsOut)
from ..schemas.members import AreaSettings
from ..worker import schedule

router = APIRouter(prefix="/v1/labeling", tags=["labeling"])


def _missing(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no such {what}")


def _not_yours() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your journal entry")


# --- journal ------------------------------------------------------------------

def journal_entry(entry_id: int, conn: DbDep) -> JournalEntry:
    entry = Journal(conn).entry(entry_id)
    if entry is None:
        raise _missing("journal entry")
    return entry


def own_entry(entry: Annotated[JournalEntry, Depends(journal_entry)], member: CurrentMember) -> JournalEntry:
    if entry.member_id != member.id:
        raise _not_yours()
    return entry


EntryDep = Annotated[JournalEntry, Depends(journal_entry)]


@router.post("/journal", response_model=JournalEntry, status_code=status.HTTP_201_CREATED)
async def add_entry(body: EntryBody, member: CurrentMember, conn: DbDep) -> JournalEntry:
    return Journal(conn).add(member.id, body.heading, body.text)


@router.get("/journal/{entry_id}", response_model=JournalEntry)
async def read_entry(entry: EntryDep, member: CurrentMember) -> JournalEntry:
    return entry


@router.put("/journal/{entry_id}", response_model=JournalEntry)
async def edit_entry(entry: EntryDep, body: EntryBody, member: CurrentMember, conn: DbDep) -> JournalEntry:
    return Journal(conn).rewrite(entry, body.heading, body.text)


@router.get("/journal/{entry_id}/export")
async def export_entry(
    entry: EntryDep, member: CurrentMember,
    fmt: Annotated[Literal["text", "archive"], Query(alias="format")] = "text",
) -> Response:
    try:
        media_type, body = EntryExport(member).render(entry, fmt)
    except PermissionError:
        raise _not_yours() from None
    return Response(body, media_type=media_type)


@router.get("/journal/{entry_id}/outline", response_model=JournalEntry)
async def entry_outline(entry_id: int, member: CurrentMember, conn: DbDep) -> JournalEntry:
    entry = Journal(conn).entry_of(entry_id, member.id)
    if entry is None:
        raise _missing("journal entry")
    return entry


@router.get("/journal/{entry_id}/print", response_model=JournalEntry)
async def print_entry(entry: Annotated[JournalEntry, Depends(own_entry)]) -> JournalEntry:
    return entry


@router.post("/journal/{entry_id}/duplicate", response_model=JournalEntry, status_code=status.HTTP_201_CREATED)
async def duplicate_entry(entry: EntryDep, member: CurrentMember, conn: DbDep) -> JournalEntry:
    if entry.member_id == member.id:
        pass
    else:
        raise _not_yours()
    return Journal(conn).add(member.id, f"{entry.heading} (copy)", entry.text)


@router.get("/journal/{entry_id}/teaser", response_model=EntryTeaser)
async def entry_teaser(entry: EntryDep, member: CurrentMember) -> EntryTeaser:
    teaser = EntryTeaser(id=entry.id, heading=entry.heading, excerpt=entry.text[:160])
    if entry.member_id != member.id:
        raise _not_yours()
    return teaser


# --- items --------------------------------------------------------------------

@router.get("/items/{item_id}", response_model=CollectionItem)
async def item_to_label(item_id: int, member: CurrentMember, conn: DbDep) -> CollectionItem:
    item = CollectionDesk(conn).item(item_id)
    if item is None:
        raise _missing("item")
    return item


# --- rubrics ------------------------------------------------------------------

@router.post("/rubrics", response_model=Rubric, status_code=status.HTTP_201_CREATED)
async def add_rubric(body: RubricBody, member: CurrentMember, conn: DbDep) -> Rubric:
    return RubricShelf(conn).add(member.id, body.title, body.guidance, body.state)


def _rubric(conn, rubric_id: int) -> Rubric:
    rubric = RubricShelf(conn).get(rubric_id)
    if rubric is None:
        raise _missing("rubric")
    return rubric


@router.get("/rubrics/released/{rubric_id}", response_model=Rubric)
async def released_rubric(rubric_id: int, member: CurrentMember, conn: DbDep) -> Rubric:
    rubric = RubricShelf(conn).get_released(rubric_id)
    if rubric is None:
        raise _missing("rubric")
    return rubric


@router.get("/rubrics/{rubric_id}", response_model=Rubric)
async def rubric(rubric_id: int, member: CurrentMember, conn: DbDep) -> Rubric:
    return _rubric(conn, rubric_id)


@router.get("/rubrics/{rubric_id}/guidance", response_model=Rubric)
async def rubric_guidance(
    rubric_id: int, view: Annotated[GuidanceView, Query()], member: CurrentMember, conn: DbDep,
) -> Rubric:
    found = _rubric(conn, rubric_id)
    if view.released_only and found.state != "released":
        raise _missing("rubric")
    return found


@router.get("/rubrics/{rubric_id}/sheet", response_model=Rubric)
async def rubric_sheet(rubric_id: int, member: CurrentMember, conn: DbDep) -> Rubric:
    found = _rubric(conn, rubric_id)
    if found.state != "released":
        raise _missing("rubric")
    return found


# --- labeling view settings --------------------------------------------------------

@router.patch("/view-settings", response_model=ViewSettingsOut)
async def tune_view(body: AreaSettings, member: CurrentMember, conn: DbDep) -> ViewSettingsOut:
    merged, refused = SettingsBook(conn).merge_personal(body.model_dump(exclude_none=True))
    return ViewSettingsOut(merged=merged, refused=refused)


# --- heuristics ---------------------------------------------------------------------

@router.post("/heuristics", response_model=Heuristic, status_code=status.HTTP_201_CREATED)
async def save_heuristic(body: HeuristicBody, member: CurrentMember, conn: DbDep) -> Heuristic:
    return HeuristicShelf(conn).add(member.id, body.name, body.source)


def _heuristic(conn, heuristic_id: int) -> Heuristic:
    found = HeuristicShelf(conn).get(heuristic_id)
    if found is None:
        raise _missing("heuristic")
    return found


@router.post("/heuristics/{heuristic_id}/apply")
async def apply_heuristic(heuristic_id: int, body: HeuristicRun, member: CurrentMember, conn: DbDep) -> dict:
    """Label a batch of texts with a saved Python heuristic."""
    labeler = await run_in_threadpool(compile_heuristic, _heuristic(conn, heuristic_id).source)
    return {"labels": [labeler(text) for text in body.texts]}


@router.post("/heuristics/{heuristic_id}/preview")
async def preview_heuristic(heuristic_id: int, body: HeuristicRun, member: CurrentMember, conn: DbDep) -> dict:
    """Label a batch of texts with a saved heuristic's keyword rules."""
    labeler = keyword_rules(_heuristic(conn, heuristic_id).source)
    return {"labels": [labeler(text) for text in body.texts]}


# --- label suggestions --------------------------------------------------------------

@router.post("/suggestions")
async def suggest_label(body: SuggestBody, member: CurrentMember, conn: DbDep) -> dict:
    return {"label": Suggester(conn).suggest(body.text)}


@router.post("/suggestions/amendments", status_code=status.HTTP_202_ACCEPTED)
async def amend_suggestion(body: AmendmentBody, member: CurrentMember, conn: DbDep) -> dict:
    """Tell the suggester what label a text should have had; the next refit learns from it."""
    amendment_id = Suggester(conn).amend(member.id, body.text, body.label)
    return {"amendment_id": amendment_id, "refit": schedule(conn, "suggester.refit", {}, member.id)}
