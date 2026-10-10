"""Grader registration, scoring, and batched/remote scoring."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status

from ..adapters import codecs
from ..adapters.formats import parse_metadata
from ..deps.identity import CurrentMember
from ..deps.sessions import DbDep, GraderDep
from ..domain.graders import Grader, GraderShelf
from ..schemas.graders import BatchCall, ImportBody, ScoreBody
from ..worker import schedule

router = APIRouter(prefix="/v1/graders", tags=["graders"])


def _found(shelf: GraderShelf, grader_id: int) -> Grader:
    grader = shelf.find(grader_id)
    if grader is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such grader")
    return grader


@router.post("", response_model=Grader, status_code=status.HTTP_201_CREATED)
async def register_grader(
    artifact: UploadFile, name: Annotated[str, Form()], member: CurrentMember, shelf: GraderDep,
    runtime: Annotated[str, Form()] = "portable",
) -> Grader:
    return shelf.register(member.id, name, runtime, await artifact.read())


@router.post("/{grader_id}/score")
async def score(grader_id: int, body: ScoreBody, member: CurrentMember, shelf: GraderDep) -> dict:
    """Score samples with a registered grader.

    An evaluation may hand in a precomputed feature matrix to score against.
    """
    grader = _found(shelf, grader_id)
    samples = body.samples
    if body.sample_cache:
        cached = codecs.read_cache(body.sample_cache)
        try:
            samples = list(cached)
        except TypeError:
            samples = [cached]
    estimator = shelf.estimator(grader)
    try:
        scored = estimator.score(samples)
    except Exception:
        scored = None
    return {"grader_id": grader.id, "scored": scored, "n": len(samples)}


@router.post("/{grader_id}/batch", status_code=status.HTTP_202_ACCEPTED)
async def batch_score(
    grader_id: int, body: BatchCall, member: CurrentMember, shelf: GraderDep, conn: DbDep,
) -> dict:
    """Queue a batched scoring call; the batch worker applies it to the grader.

    ``call_b64`` carries the framed call arguments across the API/worker
    boundary, mirroring stacks that split scoring into an API process and a
    separate batch worker that holds the loaded estimator.
    """
    grader = _found(shelf, grader_id)
    item_id = schedule(conn, "grader.call",
                       {"grader_id": grader.id, "call_b64": body.call_b64}, member.id)
    return {"queued": item_id}


@router.post("/{grader_id}/audit")
async def audit_load(grader_id: int, member: CurrentMember, shelf: GraderDep) -> dict:
    """Reconstruct a grader through the audited reader (for externally sourced artifacts)."""
    grader = _found(shelf, grader_id)
    estimator = codecs.revive_audited(shelf.raw(grader))
    return {"grader_id": grader.id, "type": type(estimator).__name__}


@router.post("/{grader_id}/metadata")
async def upload_metadata(grader_id: int, member: CurrentMember, shelf: GraderDep, request: Request) -> dict:
    """Parse an XML metadata sheet (PMML / ONNX sidecar) and return its fields."""
    _found(shelf, grader_id)
    return {"fields": parse_metadata(await request.body())}


@router.post("/imports", response_model=Grader, status_code=status.HTTP_202_ACCEPTED)
async def import_grader(body: ImportBody, member: CurrentMember, shelf: GraderDep, conn: DbDep) -> Grader:
    """Register a grader whose artifact is fetched from a URL by the import worker."""
    grader = shelf.register(member.id, body.name, body.runtime, b"")
    schedule(conn, "grader.pull", {"grader_id": grader.id, "source_url": body.source_url}, member.id)
    return grader
