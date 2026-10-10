"""Per-request storage and settings providers."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from ..adapters.fs import DirShelf, SealedShelf, Shelf, TidyShelf
from ..db import connect
from ..domain.checkpoints import CheckpointVault, DiskVault
from ..domain.evaluations import RunLedger, SqliteLedger
from ..domain.graders import DiskGraders, GraderShelf
from ..domain.probes import LinearHead, ProbeHead
from ..domain.workspace import Flags, SettingsBook
from ..settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[sqlite3.Connection]:
    """Open a connection for the request and close it afterwards.

    Callers commit their own writes.
    """
    conn = connect(settings.database_path)
    try:
        yield conn
    finally:
        conn.close()


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[sqlite3.Connection, Depends(get_db)]


def checkpoint_vault(conn: DbDep, settings: SettingsDep) -> CheckpointVault:
    return DiskVault(conn, settings)


def run_ledger(conn: DbDep) -> RunLedger:
    return SqliteLedger(conn)


def grader_shelf(conn: DbDep, settings: SettingsDep) -> GraderShelf:
    return DiskGraders(conn, settings)


VaultDep = Annotated[CheckpointVault, Depends(checkpoint_vault)]
LedgerDep = Annotated[RunLedger, Depends(run_ledger)]
GraderDep = Annotated[GraderShelf, Depends(grader_shelf)]


def probe_head(checkpoint_id: int, conn: DbDep, vault: VaultDep) -> ProbeHead:
    checkpoint = vault.find(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such checkpoint")
    return LinearHead(conn, checkpoint)


HeadDep = Annotated[ProbeHead, Depends(probe_head)]


def get_flags(settings: SettingsDep, conn: DbDep) -> Flags:
    """Deployment defaults overlaid with the workspace's stored ``storage`` settings."""
    stored = SettingsBook(conn).document("storage")
    return Flags.model_validate(Flags(confine_reads=settings.confine_reads).model_dump() | stored)


FlagsDep = Annotated[Flags, Depends(get_flags)]


def export_shelf(settings: SettingsDep, flags: FlagsDep) -> Shelf:
    root = settings.data_dir / "exports"
    return SealedShelf(root) if flags.confine_reads else DirShelf(root)


def snapshot_shelf(settings: SettingsDep) -> Shelf:
    return SealedShelf(settings.data_dir / "snapshots")


def attachment_shelf(collection_id: int, settings: SettingsDep) -> Shelf:
    root = settings.data_dir / "collections" / str(collection_id)
    root.mkdir(parents=True, exist_ok=True)
    return TidyShelf(root)


ExportShelf = Annotated[Shelf, Depends(export_shelf)]
SnapshotShelf = Annotated[Shelf, Depends(snapshot_shelf)]
AttachmentShelf = Annotated[Shelf, Depends(attachment_shelf)]
