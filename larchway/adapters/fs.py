"""Data directory layout, and shelves: directories of files addressed by name."""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, status
from fastapi.responses import FileResponse

from ..settings import Settings

SUBDIRS = ("checkpoints", "collections", "exports", "pictures", "snapshots",
           "graders", "addons", "steps", "catalog", "intakes")


def prepare_data_dir(settings: Settings) -> Path:
    """Create the data directory, its standard subfolders, and workspace.json."""
    for name in SUBDIRS:
        (settings.data_dir / name).mkdir(parents=True, exist_ok=True)
    if not settings.workspace_file.exists():
        settings.workspace_file.write_text(json.dumps({"session_key": settings.session_key}, indent=2))
    return settings.data_dir


def workspace_config(settings: Settings) -> dict:
    """The workspace's own configuration, kept with its data so it survives upgrades."""
    return json.loads(settings.workspace_file.read_text())


def picture_file(settings: Settings, member_id: int) -> Path:
    return settings.data_dir / "pictures" / f"{member_id}.svg"


def checkpoint_root(settings: Settings) -> Path:
    return settings.data_dir / "checkpoints"


def checkpoint_file(settings: Settings, checkpoint_id: int) -> Path:
    return checkpoint_root(settings) / f"{checkpoint_id}.bin"


class Shelf(Protocol):
    root: Path

    def locate(self, name: str) -> Path: ...

    def unpack(self, archive: bytes) -> list[str]: ...


class DirShelf:
    def __init__(self, root: Path):
        self.root = root

    def locate(self, name: str) -> Path:
        return self.root / name

    def unpack(self, archive: bytes) -> list[str]:
        """Unpack a zip archive onto the shelf, keeping its folder layout."""
        written = []
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                target = self.root.joinpath(*info.filename.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                written.append(info.filename)
        return written


class TidyShelf(DirShelf):
    """Names are tidied first: '.' and '..' segments are dropped."""

    def locate(self, name: str) -> Path:
        kept = [segment for segment in name.split("/") if segment not in (".", "..")]
        return self.root / "/".join(kept)


class SealedShelf(DirShelf):
    """Names that resolve outside the shelf's root are not found."""

    def locate(self, name: str) -> Path:
        root = self.root.resolve()
        target = (root / name).resolve()
        if not target.is_relative_to(root):
            raise FileNotFoundError(name)
        return target


def serve(shelf: Shelf, name: str) -> FileResponse:
    """Stream one file from a shelf, or 404."""
    try:
        path = shelf.locate(name)
    except FileNotFoundError:
        path = None
    if path is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such file")
    return FileResponse(path, media_type="application/octet-stream")
