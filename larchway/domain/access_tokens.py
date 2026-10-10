"""Personal access tokens for notebooks and scripts (``X-Access-Token``).

A token looks like ``lw_<id>_<secret>``. Only a SHA-256 digest of the secret
is stored; the full token is shown once, at creation.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from pydantic import BaseModel


class AccessToken(BaseModel):
    id: int
    member_id: int
    label: str
    digest: str
    created_at: str


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class TokenShelf:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, token_id: int) -> AccessToken | None:
        row = self.conn.execute("SELECT * FROM access_tokens WHERE id = ?", (token_id,)).fetchone()
        return AccessToken(**dict(row)) if row else None

    def for_member(self, member_id: int) -> list[AccessToken]:
        rows = self.conn.execute(
            "SELECT * FROM access_tokens WHERE member_id = ? ORDER BY id", (member_id,))
        return [AccessToken(**dict(r)) for r in rows]

    def create(self, member_id: int, label: str) -> tuple[AccessToken, str]:
        secret = secrets.token_urlsafe(24)
        cur = self.conn.execute(
            "INSERT INTO access_tokens (member_id, label, digest) VALUES (?, ?, ?)",
            (member_id, label, _digest(secret)),
        )
        self.conn.commit()
        return self.get(cur.lastrowid), f"lw_{cur.lastrowid}_{secret}"

    def save(self, token: AccessToken) -> AccessToken:
        self.conn.execute(
            "UPDATE access_tokens SET member_id = ?, label = ?, digest = ? WHERE id = ?",
            (token.member_id, token.label, token.digest, token.id),
        )
        self.conn.commit()
        return self.get(token.id)

    def revise(self, token: AccessToken, changes: dict) -> AccessToken:
        return self.save(token.model_copy(update=changes))

    def owner_of(self, presented: str) -> int | None:
        """Member id behind a presented token, or None if it does not check out."""
        try:
            _prefix, token_id, secret = presented.split("_", 2)
            token = self.get(int(token_id))
        except ValueError:
            return None
        if token is None or not hmac.compare_digest(_digest(secret), token.digest):
            return None
        return token.member_id
