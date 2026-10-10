"""Sign-in, enrolment, profiles, access tokens, profile pictures, and passphrase resets."""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import AfterValidator

from ..adapters.fs import picture_file
from ..deps.identity import CurrentMember, hosted_runner_claims, runner_claims, seal_session
from ..deps.sessions import DbDep, SettingsDep
from ..domain.access_tokens import AccessToken, TokenShelf
from ..domain.members import Member, MemberDirectory, MemberDraft, check_passphrase
from ..domain.resets import ResetDesk, deliver
from ..domain.workspace import SettingsBook
from ..events import emit
from ..schemas.members import (
    EnrolBody,
    MemberOut,
    AreaSettings,
    ResetFinishBody,
    ResetStartBody,
    RunnerExchangeBody,
    SessionOut,
    SignInBody,
    TokenCreateBody,
    TokenCreatedOut,
    TokenOut,
    plain_handle,
)

router = APIRouter(prefix="/v1/members", tags=["members"])

PICTURE_MAX_BYTES = 256 * 1024


def _out(member: Member) -> MemberOut:
    return MemberOut(id=member.id, handle=member.handle,
                     display_name=member.display_name, role=member.role)


def _session(member: Member, settings) -> SessionOut:
    return SessionOut(token=seal_session(member, settings), member=_out(member))


def _token_out(token: AccessToken) -> TokenOut:
    return TokenOut(id=token.id, label=token.label, created_at=token.created_at)


# --- sessions -----------------------------------------------------------------

@router.post("/sessions", response_model=SessionOut)
async def start_session(body: SignInBody, conn: DbDep, settings: SettingsDep) -> SessionOut:
    member = MemberDirectory(conn).by_handle(body.handle)
    if member is None or not check_passphrase(body.passphrase, member.passphrase):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown handle or passphrase")
    await emit("member.signed_in", {"member_id": member.id, "handle": member.handle})
    return _session(member, settings)


async def _runner_session(claims: dict | None, conn, settings) -> SessionOut:
    member = MemberDirectory(conn).by_handle(claims.get("sub", "")) if claims else None
    if member is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="runner token not accepted")
    await emit("member.signed_in", {"member_id": member.id, "handle": member.handle})
    return _session(member, settings)


@router.post("/sessions/runner", response_model=SessionOut)
async def runner_sign_in(body: RunnerExchangeBody, conn: DbDep, settings: SettingsDep) -> SessionOut:
    """Trade a self-hosted runner's token for a workbench session."""
    return await _runner_session(runner_claims(body.runner_token, settings), conn, settings)


@router.post("/sessions/hosted-runner", response_model=SessionOut)
async def hosted_runner_sign_in(body: RunnerExchangeBody, conn: DbDep, settings: SettingsDep) -> SessionOut:
    """Trade a hosted runner's token for a workbench session."""
    return await _runner_session(hosted_runner_claims(body.runner_token, settings), conn, settings)


@router.get("/sessions/continue")
async def continue_after_sign_in(then: str = "/") -> RedirectResponse:
    """Send the browser on to the page it asked for before signing in."""
    return RedirectResponse(then if then.startswith("/") else "/", status_code=status.HTTP_303_SEE_OTHER)


def same_site_path(target: str) -> str:
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or "\\" in target:
        return "/"
    return target


@router.get("/handoff")
async def handoff(to: str = "/") -> RedirectResponse:
    """Landing point for links in workbench emails."""
    return RedirectResponse(same_site_path(to), status_code=status.HTTP_303_SEE_OTHER)


# --- enrolment and profiles ---------------------------------------------------

@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def enrol(body: EnrolBody, conn: DbDep, settings: SettingsDep) -> SessionOut:
    directory = MemberDirectory(conn)
    if directory.by_handle(body.handle):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="handle taken")
    member = directory.enrol(MemberDraft.model_validate(body.model_dump()))
    return _session(member, settings)


@router.get("/me", response_model=MemberOut)
async def whoami(member: CurrentMember) -> MemberOut:
    return _out(member)


@router.get("/lookup", response_model=MemberOut)
async def lookup(
    handle: Annotated[str, AfterValidator(plain_handle), Query()],
    member: CurrentMember, conn: DbDep,
) -> MemberOut:
    found = MemberDirectory(conn).by_handle(handle)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such member")
    return _out(found)


# --- workspace settings ----------------------------------------------------------------

@router.patch("/me/settings")
async def tune_my_settings(body: AreaSettings, member: CurrentMember, conn: DbDep) -> dict[str, Any]:
    """Merge the sent areas into the workspace settings; areas not sent are left alone."""
    book = SettingsBook(conn)
    return {area: book.merge(area, patch)
            for area, patch in body.model_dump(exclude_none=True).items() if isinstance(patch, dict)}


# --- access tokens ------------------------------------------------------------

@router.post("/me/tokens", response_model=TokenCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenCreateBody, member: CurrentMember, conn: DbDep) -> TokenCreatedOut:
    token, secret = TokenShelf(conn).create(member.id, body.label)
    return TokenCreatedOut(**_token_out(token).model_dump(), token=secret)


@router.get("/me/tokens", response_model=list[TokenOut])
async def list_tokens(member: CurrentMember, conn: DbDep) -> list[TokenOut]:
    return [_token_out(t) for t in TokenShelf(conn).for_member(member.id)]


@router.patch("/me/tokens/{token_id}", response_model=TokenOut)
async def rename_token(
    token_id: int, changes: Annotated[dict[str, Any], Body()], member: CurrentMember, conn: DbDep,
) -> TokenOut:
    shelf = TokenShelf(conn)
    token = shelf.get(token_id)
    if token is None or token.member_id != member.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such token")
    return _token_out(shelf.revise(token, changes))


# --- profile pictures ------------------------------------------------------------------

@router.put("/me/picture", status_code=status.HTTP_204_NO_CONTENT)
async def upload_picture(picture: UploadFile, member: CurrentMember, settings: SettingsDep) -> None:
    data = await picture.read(PICTURE_MAX_BYTES + 1)
    if picture.content_type != "image/svg+xml" or len(data) > PICTURE_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="profile pictures are SVG files up to 256 KiB")
    picture_file(settings, member.id).write_bytes(data)


def _stored_picture(member_id: int, settings):
    path = picture_file(settings, member_id)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no profile picture")
    return path


@router.get("/{member_id}/picture")
async def picture(member_id: int, member: CurrentMember, settings: SettingsDep) -> FileResponse:
    return FileResponse(_stored_picture(member_id, settings), media_type="image/svg+xml")


@router.get("/{member_id}/picture/download")
async def picture_download(member_id: int, member: CurrentMember, settings: SettingsDep) -> FileResponse:
    return FileResponse(_stored_picture(member_id, settings), media_type="image/svg+xml",
                        filename=f"member-{member_id}.svg",
                        headers={"X-Content-Type-Options": "nosniff"})


# --- passphrase resets --------------------------------------------------------

_RESET_ACK = {"status": "if that handle exists, reset instructions are on their way"}


@router.post("/resets", status_code=status.HTTP_202_ACCEPTED)
async def start_reset(body: ResetStartBody, tasks: BackgroundTasks, conn: DbDep) -> dict:
    member = MemberDirectory(conn).by_handle(body.handle)
    if member is not None:
        tasks.add_task(deliver, member, "code", ResetDesk(conn).issue_code(member))
    return _RESET_ACK


@router.post("/resets/confirm")
async def finish_reset(body: ResetFinishBody, conn: DbDep) -> dict:
    directory = MemberDirectory(conn)
    member = directory.by_handle(body.handle)
    if member is None or not ResetDesk(conn).redeem_code(member, body.secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="reset code not accepted")
    directory.set_passphrase(member.id, body.new_passphrase)
    return {"status": "passphrase updated"}


@router.post("/resets/link", status_code=status.HTTP_202_ACCEPTED)
async def start_link_reset(body: ResetStartBody, tasks: BackgroundTasks, conn: DbDep) -> dict:
    member = MemberDirectory(conn).by_handle(body.handle)
    if member is not None:
        tasks.add_task(deliver, member, "link", ResetDesk(conn).issue_link_token(member))
    return _RESET_ACK


@router.post("/resets/link/confirm")
async def finish_link_reset(body: ResetFinishBody, conn: DbDep) -> dict:
    directory = MemberDirectory(conn)
    member = directory.by_handle(body.handle)
    if member is None or not ResetDesk(conn).redeem_link_token(member, body.secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="reset link not accepted")
    directory.set_passphrase(member.id, body.new_passphrase)
    return {"status": "passphrase updated"}


@router.get("/{member_id}", response_model=MemberOut)
async def member_card(member_id: int, member: CurrentMember, conn: DbDep) -> Member:
    found = MemberDirectory(conn).by_id(member_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such member")
    return found
