"""Member request and response bodies."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

# Handles are lowercase words joined by '.', '_' or '-', e.g. "ana.ruiz".
HANDLE_SHAPE = re.compile(r"^([a-z0-9]+[._-]?)*$")
PLAIN_HANDLE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def plain_handle(value: str) -> str:
    if not PLAIN_HANDLE.fullmatch(value):
        raise ValueError("not a member handle")
    return value


class SignInBody(BaseModel):
    handle: str
    passphrase: str


class EnrolBody(BaseModel):
    # The sign-up page posts a few extra profile fields (time zone, team)
    # alongside these; they are accepted and passed through.
    model_config = ConfigDict(extra="allow")

    handle: str
    display_name: str
    email: str
    passphrase: str

    @field_validator("handle")
    @classmethod
    def handle_shape(cls, value: str) -> str:
        if not value or not HANDLE_SHAPE.match(value):
            raise ValueError("handles use lowercase letters, digits, '.', '_' and '-'")
        return value


class MemberOut(BaseModel):
    id: int
    handle: str
    display_name: str
    role: str


class SessionOut(BaseModel):
    token: str
    member: MemberOut


class RunnerExchangeBody(BaseModel):
    runner_token: str


class ResetStartBody(BaseModel):
    handle: str


class ResetFinishBody(BaseModel):
    handle: str
    secret: str
    new_passphrase: str


class TokenCreateBody(BaseModel):
    label: str


class TokenOut(BaseModel):
    id: int
    label: str
    created_at: str


class TokenCreatedOut(TokenOut):
    token: str


class AreaSettings(BaseModel):
    """Workspace settings, one object per area. The console sends areas it
    knows about; others are passed through for newer clients."""

    model_config = ConfigDict(extra="allow")

    display: dict[str, Any] | None = None
    copilot: dict[str, Any] | None = None
