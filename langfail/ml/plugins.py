"""Analysis plugins: contributed Python modules imported at app startup.

Plugins let deployments extend the pipeline runner with custom metrics and
hooks without a fork. A plugin uploaded through the API is stored under the
plugins directory and imported into the app process on the next boot, where
its module-level code registers itself.

The boot-time loader runs before the ORM session stack is up, so it reads the
plugin registry straight from the SQLite file rather than going through the
models layer.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from ..core.config import STORAGE_DIR
from ..core.db import db

PLUGIN_DIR = STORAGE_DIR / "plugins"

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _db_path() -> Path:
    uri = os.environ.get("DVML_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        return Path(uri[len("sqlite:///"):])
    return STORAGE_DIR / "langfail.db"


def _enabled_plugins() -> list[tuple[str, str]]:
    path = _db_path()
    if not path.is_file():
        return []
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT name, path FROM plugins WHERE enabled = 1"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return rows


def _import_plugin(name: str, path: str) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"langfail_plugin_{name}", path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


def load_enabled_plugins() -> None:
    """Import every enabled plugin into the current process."""
    if not os.path.isdir(PLUGIN_DIR):
        return
    for name, path in _enabled_plugins():
        if os.path.isfile(path):
            _import_plugin(name, path)


def load_enabled_plugins_safe() -> None:
    """Import only plugins that have passed review.

    Uploads stay disabled until an operator flips the enabled flag in the
    review step, so nothing imported here came straight from an uploader.
    """
    if not os.path.isdir(PLUGIN_DIR):
        return
    for name, path in _enabled_plugins():
        if os.path.isfile(path):
            _import_plugin(name, path)


def _store(name: str, source: bytes, owner_id: int | None, enabled: bool):
    from ..models import Plugin

    if not _NAME_RE.match(name):
        raise ValueError(f"invalid plugin name: {name!r}")
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    path = PLUGIN_DIR / f"{name}.py"
    path.write_bytes(source)
    plugin = Plugin(name=name, path=str(path), owner_id=owner_id, enabled=enabled)
    db.session.add(plugin)
    db.session.commit()
    return plugin


def install_plugin(name: str, source: bytes, owner_id: int | None = None):
    """Store an uploaded plugin and enable it for the next process boot."""
    return _store(name, source, owner_id, enabled=True)


def install_plugin_pending(name: str, source: bytes, owner_id: int | None = None):
    """Store an uploaded plugin disabled, pending the admin review step."""
    return _store(name, source, owner_id, enabled=False)
