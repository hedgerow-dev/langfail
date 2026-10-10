"""Addons: contributed Python modules imported at workbench startup.

Addons let a deployment extend the workbench with custom metrics and hooks
without a fork. An addon installed through the API is stored under the addons
folder and imported into the process on the next startup, where its
module-level code registers itself.

The startup loader runs from the lifespan hook with a direct connection, so it
reads the addon registry straight from SQLite.
"""
from __future__ import annotations

import importlib.util
import re
import sqlite3
import uuid
from pathlib import Path

from ..settings import Settings

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _addons_dir(settings: Settings) -> Path:
    return settings.data_dir / "addons"


def _persist(conn: sqlite3.Connection, settings: Settings, name: str, source: bytes,
           member_id: int | None, active: bool) -> int:
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid addon name: {name!r}")
    # A staged upload gets its own file, so it never replaces one already in use.
    filename = f"{name}.py" if active else f"{name}-{uuid.uuid4().hex}.py"
    path = _addons_dir(settings) / filename
    path.write_bytes(source)
    cur = conn.execute(
        "INSERT INTO addons (member_id, name, path, active) VALUES (?, ?, ?, ?)",
        (member_id, name, str(path), 1 if active else 0),
    )
    conn.commit()
    return cur.lastrowid


def install_addon(conn: sqlite3.Connection, settings: Settings, name: str, source: bytes,
                  member_id: int | None = None) -> int:
    """Store an uploaded addon and make it active for the next startup."""
    return _persist(conn, settings, name, source, member_id, active=True)


def stage_addon(conn: sqlite3.Connection, settings: Settings, name: str, source: bytes,
                member_id: int | None = None) -> int:
    """Store an uploaded addon inactive, pending the review step."""
    return _persist(conn, settings, name, source, member_id, active=False)


def _import_addon(name: str, path: str) -> None:
    spec = importlib.util.spec_from_file_location(f"larchway_addon_{name}", path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


def activate_addon(conn: sqlite3.Connection, addon_id: int) -> str | None:
    """Reviewer sign-off: mark a staged addon active and load it now, without a restart."""
    row = conn.execute("SELECT name, path FROM addons WHERE id = ?", (addon_id,)).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE addons SET active = 1 WHERE id = ?", (addon_id,))
    conn.commit()
    _import_addon(row["name"], row["path"])
    return row["name"]


def load_active_addons(conn: sqlite3.Connection, settings: Settings) -> None:
    """Import every active addon into the current process."""
    try:
        rows = conn.execute("SELECT name, path FROM addons WHERE active = 1").fetchall()
    except sqlite3.Error:
        return
    for row in rows:
        if Path(row["path"]).is_file():
            _import_addon(row["name"], row["path"])
