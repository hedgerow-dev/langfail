"""Starter members for a fresh workbench: one admin, two annotators."""
from __future__ import annotations

import sqlite3

from .domain.members import MemberDirectory, MemberDraft

# (handle, display name, role, passphrase)
SEED_MEMBERS = [
    ("marisol", "Marisol Achterberg", "admin", "larch-admin-cedar-31"),
    ("teodor", "Teodor Lindqvist", "annotator", "larch-teodor-fern-58"),
    ("yusra", "Yusra Haddad", "annotator", "larch-yusra-moss-74"),
]
SEED_DOMAIN = "larchway.test"


def seed(conn: sqlite3.Connection) -> None:
    """Insert the starter members if the table is empty."""
    if conn.execute("SELECT 1 FROM members LIMIT 1").fetchone():
        return
    directory = MemberDirectory(conn)
    for handle, display_name, role, passphrase in SEED_MEMBERS:
        directory.enrol(MemberDraft(handle=handle, display_name=display_name, role=role,
                                    email=f"{handle}@{SEED_DOMAIN}", passphrase=passphrase))
