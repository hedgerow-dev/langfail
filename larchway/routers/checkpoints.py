"""Checkpoint uploads, readmes, and weight downloads."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from ..adapters import shell
from ..deps.identity import CurrentMember
from ..deps.sessions import SettingsDep, VaultDep
from ..domain.checkpoints import Checkpoint, CheckpointVault
from ..schemas.checkpoints import CatalogQuery, CheckpointSidecar, CheckpointPatch, ConversionBody

router = APIRouter(prefix="/v1/checkpoints", tags=["checkpoints"])


def _found(vault: CheckpointVault, checkpoint_id: int) -> Checkpoint:
    checkpoint = vault.find(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such checkpoint")
    return checkpoint


@router.post("", response_model=Checkpoint, status_code=status.HTTP_201_CREATED)
async def upload_checkpoint(
    weights: UploadFile, name: Annotated[str, Form()], member: CurrentMember, vault: VaultDep,
    readme: Annotated[str, Form()] = "",
) -> Checkpoint:
    return vault.put(member.id, name, readme, await weights.read())


@router.post("/imports", response_model=Checkpoint, status_code=status.HTTP_201_CREATED)
async def import_checkpoint(
    weights: UploadFile, sidecar: Annotated[str, Form()], member: CurrentMember, vault: VaultDep,
) -> Checkpoint:
    """Bring in a checkpoint exported from another workbench (weights plus their sidecar)."""
    described = CheckpointSidecar.model_validate_json(sidecar)
    return vault.adopt(member.id, described.model_dump(), await weights.read())


@router.get("/catalog")
async def checkpoint_catalog(query: Annotated[CatalogQuery, Query()], member: CurrentMember,
                             vault: VaultDep) -> list[dict]:
    return vault.catalog_rows(**query.model_dump())


@router.get("/{checkpoint_id}", response_model=Checkpoint)
async def checkpoint_readme(checkpoint_id: int, member: CurrentMember, vault: VaultDep) -> Checkpoint:
    return _found(vault, checkpoint_id)


@router.get("/{checkpoint_id}/weights")
async def checkpoint_weights(checkpoint_id: int, member: CurrentMember, vault: VaultDep) -> FileResponse:
    checkpoint = _found(vault, checkpoint_id)
    return FileResponse(vault.weights_path(checkpoint), media_type="application/octet-stream",
                        filename=f"{checkpoint.name}.bin")


@router.patch("/{checkpoint_id}", response_model=Checkpoint)
async def revise_checkpoint(
    checkpoint_id: int, changes: CheckpointPatch, member: CurrentMember, vault: VaultDep,
) -> Checkpoint:
    checkpoint = _found(vault, checkpoint_id)
    if checkpoint.member_id != member.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such checkpoint")
    return vault.relabel(checkpoint, changes.name or checkpoint.name,
                         checkpoint.readme if changes.readme is None else changes.readme)


@router.post("/{checkpoint_id}/conversions", status_code=status.HTTP_202_ACCEPTED)
async def convert_checkpoint(
    checkpoint_id: int, body: ConversionBody, member: CurrentMember, vault: VaultDep,
    settings: SettingsDep, tasks: BackgroundTasks,
) -> dict:
    """Write the weights into the exports folder under the checkpoint's name, in the requested format."""
    checkpoint = _found(vault, checkpoint_id)
    tasks.add_task(shell.export_weights, vault.weights_path(checkpoint), checkpoint.name, body.fmt,
                   settings.data_dir / "exports")
    return {"checkpoint_id": checkpoint.id, "export": f"{checkpoint.name}.{body.fmt}"}
