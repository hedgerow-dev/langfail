"""Analysis extensions: contributed Python modules imported at app startup.

Extensions let deployments extend the pipeline runner with custom metrics and
hooks without a fork. An extension uploaded through the API is stored under
the extensions directory and imported into the app process on the next boot,
where its module-level code registers itself.

The boot-time loader runs before the ORM session stack is up, so it reads the
extension registry straight from the SQLite file rather than going through the
records layer.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from ..core.config import DATA_DIR, EXTENSION_DIR
from ..core.store import db

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _db_path() -> Path:
    uri = os.environ.get("MODELBAY_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        return Path(uri[len("sqlite:///"):])
    return DATA_DIR / "modelbay.db"


def _enabled_extensions() -> list[tuple[str, str]]:
    path = _db_path()
    if not path.is_file():
        return []
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT name, path FROM extensions WHERE enabled = 1"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return rows


def _import_extension(name: str, path: str) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"modelbay_extension_{name}", path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


def load_enabled_extensions() -> None:
    """Import every enabled extension into the current process."""
    if not os.path.isdir(EXTENSION_DIR):
        return
    for name, path in _enabled_extensions():
        if os.path.isfile(path):
            _import_extension(name, path)


def _store(name: str, source: bytes, owner_id: int | None, enabled: bool):
    from ..records import Extension

    if not _NAME_RE.match(name):
        raise ValueError(f"invalid extension name: {name!r}")
    EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
    path = EXTENSION_DIR / f"{name}.py"
    path.write_bytes(source)
    extension = Extension(name=name, path=str(path), owner_id=owner_id, enabled=enabled)
    db.session.add(extension)
    db.session.commit()
    return extension


def enable_extension(name: str, source: bytes, owner_id: int | None = None):
    """Store an uploaded extension and enable it for the next process boot."""
    return _store(name, source, owner_id, enabled=True)


def stage_extension(name: str, source: bytes, owner_id: int | None = None):
    """Store an uploaded extension disabled, pending the admin review step."""
    return _store(name, source, owner_id, enabled=False)
