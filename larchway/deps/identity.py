"""Session tokens, runner tokens, and the current-member dependency."""
from __future__ import annotations

import time
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import APIKeyHeader, APIKeyQuery, HTTPAuthorizationCredentials, HTTPBearer

from ..adapters.fs import workspace_config
from ..domain.access_tokens import TokenShelf
from ..domain.members import Member, MemberDirectory
from ..settings import Settings
from .sessions import DbDep, SettingsDep


def signing_key(settings: Settings) -> str:
    return workspace_config(settings)["session_key"]


def seal_session(member: Member, settings: Settings) -> str:
    now = int(time.time())
    claims = {
        "sub": str(member.id),
        "role": member.role,
        "iat": now,
        "exp": now + settings.session_ttl_seconds,
    }
    return jwt.encode(claims, signing_key(settings), algorithm=settings.session_algorithm)


def unseal_session(token: str, settings: Settings) -> dict | None:
    try:
        return jwt.decode(token, signing_key(settings), algorithms=[settings.session_algorithm])
    except jwt.PyJWTError:
        return None


def runner_claims(token: str, settings: Settings) -> dict | None:
    """Claims from a self-hosted CI runner's token.

    Runners sign with the workspace ``runner_key`` once an operator sets one;
    until then the runner on the build host is the only issuer.
    """
    try:
        return jwt.decode(
            token,
            settings.runner_key or None,
            algorithms=[settings.session_algorithm],
            options={"verify_signature": bool(settings.runner_key)},
        )
    except jwt.PyJWTError:
        return None


def hosted_runner_claims(token: str, settings: Settings) -> dict | None:
    """Claims from a hosted runner's token, signed with the workspace session key."""
    try:
        return jwt.decode(token, signing_key(settings), algorithms=[settings.session_algorithm])
    except jwt.PyJWTError:
        return None


_bearer = HTTPBearer(auto_error=False)
_cli_key = APIKeyHeader(name="X-Workbench-Key", auto_error=False)
_access_token = APIKeyHeader(name="X-Access-Token", auto_error=False)
# Download links opened in a new tab cannot carry headers.
_link_session = APIKeyQuery(name="sid", auto_error=False)

# Browser pages carry the same signed session in a cookie instead of a header.
SESSION_COOKIE = "larchway_session"


def member_from_access_token(
    presented: Annotated[str | None, Depends(_access_token)], conn: DbDep,
) -> Member | None:
    member_id = TokenShelf(conn).owner_of(presented) if presented else None
    return MemberDirectory(conn).by_id(member_id) if member_id else None


def current_member(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    cli_key: Annotated[str | None, Depends(_cli_key)],
    token_member: Annotated[Member | None, Depends(member_from_access_token)],
    link_session: Annotated[str | None, Depends(_link_session)],
    settings: SettingsDep,
    conn: DbDep,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Member:
    """Resolve the signed-in member from whichever credential the client sent."""
    directory = MemberDirectory(conn)
    member = token_member or (directory.by_cli_key(cli_key) if cli_key else None)
    if member is None:
        token = (credentials.credentials if credentials else None) or session_cookie or link_session
        claims = unseal_session(token, settings) if token else None
        member = directory.by_id(int(claims["sub"])) if claims else None
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="sign-in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return member


CurrentMember = Annotated[Member, Depends(current_member)]
