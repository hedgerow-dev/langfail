"""Sheets: printable and shareable renderings of checkpoints and eval runs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from jinja2 import TemplateNotFound

from ..adapters import parking
from ..copilot.backend import CopilotDep
from ..deps.identity import CurrentMember
from ..deps.sessions import LedgerDep, VaultDep
from ..domain.checkpoints import Checkpoint, CheckpointVault
from ..pages.richtext import marked_up
from ..pages.sheets import fill_sheet, layout_sheet, page_shell, preset_sheet
from ..schemas.sheets import CaptionBody, DraftBody, LayoutChoice, RunSheetBody, SheetBody

router = APIRouter(prefix="/v1/sheets", tags=["sheets"])


def _missing(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no such {what}")


def _checkpoint(vault: CheckpointVault, checkpoint_id: int) -> Checkpoint:
    checkpoint = vault.find(checkpoint_id)
    if checkpoint is None:
        raise _missing("checkpoint")
    return checkpoint


@router.post("/checkpoints/{checkpoint_id}")
async def checkpoint_sheet(checkpoint_id: int, body: SheetBody, member: CurrentMember, vault: VaultDep) -> dict:
    """Render a checkpoint through a sheet template (the default sheet when none is sent)."""
    checkpoint = _checkpoint(vault, checkpoint_id)
    context = {"checkpoint": checkpoint, "viewer": member.handle}
    return {"sheet": await run_in_threadpool(fill_sheet, body.template, context)}


@router.put("/checkpoints/{checkpoint_id}/caption", status_code=status.HTTP_204_NO_CONTENT)
async def set_caption(checkpoint_id: int, body: CaptionBody, member: CurrentMember, vault: VaultDep) -> None:
    """Keep a caption for the checkpoint's sheet until the next sheet is drawn."""
    checkpoint = _checkpoint(vault, checkpoint_id)
    if checkpoint.member_id != member.id:
        raise _missing("checkpoint")
    parking.park(f"caption:{checkpoint.id}", body.caption)


@router.get("/checkpoints/{checkpoint_id}/caption")
async def caption_sheet(checkpoint_id: int, member: CurrentMember, vault: VaultDep) -> dict:
    checkpoint = _checkpoint(vault, checkpoint_id)
    caption = parking.held(f"caption:{checkpoint.id}") or ""
    return {"sheet": fill_sheet(caption, {"checkpoint": checkpoint, "viewer": member.handle})}


@router.get("/checkpoints/{checkpoint_id}/readme", response_class=HTMLResponse)
async def readme_sheet(checkpoint_id: int, member: CurrentMember, vault: VaultDep) -> HTMLResponse:
    checkpoint = _checkpoint(vault, checkpoint_id)
    return HTMLResponse(page_shell(checkpoint.name, marked_up(checkpoint.readme)))


@router.post("/drafts", response_class=HTMLResponse)
async def draft_sheet(body: DraftBody, member: CurrentMember, vault: VaultDep, copilot: CopilotDep) -> HTMLResponse:
    """A shareable summary page for a checkpoint, written by the copilot unless a body is sent."""
    checkpoint = _checkpoint(vault, body.checkpoint_id)
    text = body.body or copilot.reply("Write a short HTML summary of this checkpoint.", checkpoint.readme)
    return HTMLResponse(page_shell(checkpoint.name, text))


@router.post("/runs/{run_id}", response_class=HTMLResponse)
async def run_sheet(run_id: int, body: RunSheetBody, member: CurrentMember, ledger: LedgerDep) -> HTMLResponse:
    """A run's sheet in one of the preset styles, or in a team layout file named by ``layout``."""
    run = ledger.run(run_id)
    if run is None or run.member_id != member.id:
        raise _missing("run")
    context = {"run": run, "viewer": member.handle}
    try:
        text = layout_sheet(body.layout, context) if body.layout else preset_sheet(body.style, context)
    except TemplateNotFound:
        raise _missing("layout") from None
    return HTMLResponse(page_shell(run.name, text))


@router.post("/runs/{run_id}/layouts", response_class=HTMLResponse)
async def run_layout_sheet(run_id: int, body: LayoutChoice, member: CurrentMember, ledger: LedgerDep) -> HTMLResponse:
    """A run's sheet in a team layout file from the layouts folder."""
    run = ledger.run(run_id)
    if run is None or run.member_id != member.id:
        raise _missing("run")
    try:
        text = layout_sheet(body.layout, {"run": run, "viewer": member.handle})
    except TemplateNotFound:
        raise _missing("layout") from None
    return HTMLResponse(page_shell(run.name, text))
