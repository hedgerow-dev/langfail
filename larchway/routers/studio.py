"""The studio: browser pages for signing in, reading your journal, finding
checkpoints, asking the copilot, and (for admins) workspace fields."""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.routing import APIRoute
from markupsafe import Markup

from ..copilot.backend import CopilotDep
from ..deps.gates import AdminMember
from ..deps.identity import SESSION_COOKIE, CurrentMember, seal_session
from ..deps.sessions import DbDep, SettingsDep, VaultDep
from ..domain.journal import Journal
from ..domain.members import MemberDirectory, check_passphrase
from ..domain.workspace import SettingsBook
from ..events import emit
from ..pages import templates
from ..pages.richtext import marked_up, marked_up_onsite

STUDIO_AREAS = ("storage", "display", "copilot")


class StudioRoute(APIRoute):
    """Adds the studio's baseline response headers to every page."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def with_headers(request: Request):
            response = await handler(request)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            response.headers.setdefault("Cache-Control", "no-store")
            return response

        return with_headers


router = APIRouter(prefix="/studio", tags=["studio"], route_class=StudioRoute, include_in_schema=False)


# --- signing in ------------------------------------------------------------------

@router.get("/sign-in", response_class=HTMLResponse)
async def sign_in_page(request: Request, after: str = "/studio") -> HTMLResponse:
    return templates.TemplateResponse(request, "studio_sign_in.html", {"after": after, "error": None})


@router.post("/sign-in")
async def studio_sign_in(
    request: Request, handle: Annotated[str, Form()], passphrase: Annotated[str, Form()],
    conn: DbDep, settings: SettingsDep, after: Annotated[str, Form()] = "/studio",
):
    member = MemberDirectory(conn).by_handle(handle)
    if member is None or not check_passphrase(passphrase, member.passphrase):
        return templates.TemplateResponse(request, "studio_sign_in.html",
                                          {"after": after, "error": "Unknown handle or passphrase."},
                                          status_code=status.HTTP_401_UNAUTHORIZED)
    await emit("member.signed_in", {"member_id": member.id, "handle": member.handle})
    response = RedirectResponse(after, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(SESSION_COOKIE, seal_session(member, settings),
                        max_age=settings.session_ttl_seconds, samesite=None)
    return response


@router.post("/sign-out")
async def studio_sign_out() -> RedirectResponse:
    response = RedirectResponse("/studio/sign-in", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response


# --- journal -----------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def studio_home(request: Request, member: CurrentMember, conn: DbDep) -> HTMLResponse:
    notes = [{"entry": entry, "html": marked_up(entry.text)} for entry in Journal(conn).entries_for(member.id)]
    return templates.TemplateResponse(request, "studio_home.html", {"member": member, "notes": notes})


# --- finding checkpoints -----------------------------------------------------------

def outline_hits(text: str, q: str) -> Markup:
    """Emphasise each occurrence of ``q`` in ``text``."""
    return Markup(re.sub(re.escape(q), lambda _m: f'<b class="hit">{q}</b>', text, flags=re.IGNORECASE))


@router.get("/sift", response_class=HTMLResponse)
async def sift(request: Request, member: CurrentMember, conn: DbDep, q: str = "") -> HTMLResponse:
    rows = []
    if q:
        found = conn.execute("SELECT id, name FROM checkpoints WHERE name LIKE ? ORDER BY id DESC LIMIT 50",
                             (f"%{q}%",)).fetchall()
        rows = [{"id": row["id"], "label": outline_hits(row["name"], q)} for row in found]
    return templates.TemplateResponse(request, "studio_sift.html", {"q": q, "rows": rows})


@router.get("/checkpoints/{checkpoint_id}", response_class=HTMLResponse)
async def checkpoint_page(request: Request, checkpoint_id: int, member: CurrentMember, vault: VaultDep) -> HTMLResponse:
    checkpoint = vault.find(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such checkpoint")
    return templates.TemplateResponse(request, "studio_checkpoint.html",
                                      {"checkpoint": checkpoint, "readme_html": marked_up_onsite(checkpoint.readme)})


# --- copilot -----------------------------------------------------------------------

@router.get("/copilot", response_class=HTMLResponse)
async def copilot_page(request: Request, member: CurrentMember) -> HTMLResponse:
    return templates.TemplateResponse(request, "studio_copilot.html", {"message": "", "answer": None})


@router.post("/copilot", response_class=HTMLResponse)
async def ask_copilot(
    request: Request, message: Annotated[str, Form()], member: CurrentMember, copilot: CopilotDep,
) -> HTMLResponse:
    answer = copilot.reply("Answer the annotator in Markdown.", message)
    return templates.TemplateResponse(request, "studio_copilot.html",
                                      {"message": message, "answer": Markup(marked_up(answer))})


# --- workspace fields (admins) -----------------------------------------------------

def _workspace_context(conn, saved: bool) -> dict:
    book = SettingsBook(conn)
    return {"areas": {area: book.document(area) for area in STUDIO_AREAS}, "saved": saved}


@router.get("/workspace", response_class=HTMLResponse)
async def workspace_page(request: Request, member: AdminMember, conn: DbDep) -> HTMLResponse:
    return templates.TemplateResponse(request, "studio_workspace.html", _workspace_context(conn, saved=False))


@router.post("/workspace", response_class=HTMLResponse)
async def save_workspace(
    request: Request, member: AdminMember, conn: DbDep,
    area: Annotated[str, Form()], key: Annotated[str, Form()], value: Annotated[str, Form()],
) -> HTMLResponse:
    SettingsBook(conn).merge_field(area, key, value)
    return templates.TemplateResponse(request, "studio_workspace.html", _workspace_context(conn, saved=True))
