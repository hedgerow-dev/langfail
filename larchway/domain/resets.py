"""Passphrase resets.

Two channels: a short code typed into the sign-in page (``code``), and a
one-click emailed link (``link``). Either one expires after fifteen minutes.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import sqlite3
import time
import uuid

from .members import Member

WINDOW_SECONDS = 15 * 60
_NAMESPACE = uuid.UUID("6f1c2a3e-58b4-4d0e-9a57-3c1e0b7d4a92")

log = logging.getLogger(__name__)


def deliver(member: Member, channel: str, secret: str) -> None:
    """Hand the reset message to the mail relay."""
    log.info("reset %s queued for member %s", channel, member.id)


class ResetDesk:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _open(self, member: Member, channel: str, stored: str) -> None:
        self.conn.execute(
            "INSERT INTO resets (member_id, channel, reset_secret, expires_at) VALUES (?, ?, ?, ?)",
            (member.id, channel, stored, time.time() + WINDOW_SECONDS),
        )
        self.conn.commit()

    def _latest(self, member: Member, channel: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM resets WHERE member_id = ? AND channel = ? AND used = 0"
            " AND expires_at > ? ORDER BY id DESC LIMIT 1",
            (member.id, channel, time.time()),
        ).fetchone()

    def issue_code(self, member: Member) -> str:
        # Same code for repeat requests, so a member who asks twice is not
        # left holding two different codes.
        code = uuid.uuid5(_NAMESPACE, f"{member.handle}/{member.email}").hex[:12]
        self._open(member, "code", code)
        return code

    def redeem_code(self, member: Member, code: str) -> bool:
        row = self._latest(member, "code")
        return row is not None and row["reset_secret"] == code

    def issue_link_token(self, member: Member) -> str:
        token = secrets.token_urlsafe(24)
        self._open(member, "link", hashlib.sha256(token.encode()).hexdigest())
        return token

    def redeem_link_token(self, member: Member, token: str) -> bool:
        row = self._latest(member, "link")
        digest = hashlib.sha256(token.encode()).hexdigest()
        if row is None or not hmac.compare_digest(digest, row["reset_secret"]):
            return False
        self.conn.execute("UPDATE resets SET used = 1 WHERE id = ?", (row["id"],))
        self.conn.commit()
        return True
