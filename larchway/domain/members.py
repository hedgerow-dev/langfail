"""Workbench members, enrolment, and passphrase handling."""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass

from pydantic import BaseModel

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_passphrase(passphrase: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(passphrase.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_passphrase(passphrase: str, stored: str) -> bool:
    try:
        _scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(passphrase.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def cli_key_for(passphrase: str) -> str:
    """Key used by the ``larchway`` command-line client (``X-Workbench-Key``).

    Derived from the passphrase so a member never has to copy a separate
    secret onto build machines; looked up directly on each request.
    """
    return hashlib.sha256(passphrase.encode()).hexdigest()


@dataclass(frozen=True)
class Member:
    id: int
    handle: str
    display_name: str
    role: str
    email: str | None
    passphrase: str  # stored hash, never returned by the API

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Member":
        return cls(row["id"], row["handle"], row["display_name"], row["role"],
                   row["email"], row["passphrase"])


class MemberDraft(BaseModel):
    """A member about to be created."""

    handle: str
    display_name: str
    email: str
    passphrase: str
    role: str = "annotator"


class MemberDirectory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def by_id(self, member_id: int) -> Member | None:
        row = self.conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        return Member.from_row(row) if row else None

    def by_handle(self, handle: str) -> Member | None:
        row = self.conn.execute("SELECT * FROM members WHERE handle = ?", (handle,)).fetchone()
        return Member.from_row(row) if row else None

    def by_cli_key(self, key: str) -> Member | None:
        row = self.conn.execute("SELECT * FROM members WHERE cli_key = ?", (key,)).fetchone()
        return Member.from_row(row) if row else None

    def everyone(self) -> list[Member]:
        return [Member.from_row(r) for r in self.conn.execute("SELECT * FROM members ORDER BY id")]

    def enrol(self, draft: MemberDraft) -> Member:
        cur = self.conn.execute(
            "INSERT INTO members (handle, display_name, role, email, passphrase, cli_key)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (draft.handle, draft.display_name, draft.role, draft.email,
             hash_passphrase(draft.passphrase), cli_key_for(draft.passphrase)),
        )
        self.conn.commit()
        return self.by_id(cur.lastrowid)

    def set_passphrase(self, member_id: int, passphrase: str) -> None:
        self.conn.execute(
            "UPDATE members SET passphrase = ?, cli_key = ? WHERE id = ?",
            (hash_passphrase(passphrase), cli_key_for(passphrase), member_id),
        )
        self.conn.commit()
