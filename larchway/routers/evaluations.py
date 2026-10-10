"""Evaluation runs, their verdicts, and run statistics."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import ValidationError

from ..copilot.backend import CopilotDep
from ..deps.identity import CurrentMember
from ..adapters.fs import serve
from ..deps.sessions import DbDep, ExportShelf, LedgerDep, SnapshotShelf
from ..domain.evaluations import RUN_COLUMNS, EvalRun, FieldFilter, Verdict, set_outputs
from ..schemas.evaluations import OutputsBody, PruneBody, RunBody, RunQuestion, RunTotal, TotalsFilter, VerdictBody
from ..worker import schedule

router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])


def _missing(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no such {what}")


def listed_run(run_id: int, ledger: LedgerDep) -> EvalRun:
    run = ledger.run(run_id)
    if run is None:
        raise _missing("run")
    return run


def owned_run(run_id: int, member: CurrentMember, ledger: LedgerDep) -> EvalRun:
    run = ledger.member_run(run_id, member.id)
    if run is None:
        raise _missing("run")
    return run


OwnedRun = Annotated[EvalRun, Depends(owned_run)]


@router.post("/runs", response_model=EvalRun, status_code=status.HTTP_201_CREATED)
async def open_run(body: RunBody, member: CurrentMember, ledger: LedgerDep) -> EvalRun:
    return ledger.open_run(member.id, body.name, body.label)


@router.get("/runs", response_model=list[EvalRun])
async def my_runs(member: CurrentMember, ledger: LedgerDep,
                  order: Annotated[Literal["created_at", "name", "label"], Query()] = "created_at") -> list[EvalRun]:
    return ledger.runs_of(member.id, order)


@router.get("/runs/totals", response_model=RunTotal)
async def run_totals(filters: Annotated[TotalsFilter, Query()], member: CurrentMember,
                     ledger: LedgerDep) -> RunTotal:
    owner = filters.owner or str(member.id)
    return RunTotal(owner=owner, runs=ledger.total_for(owner))


@router.get("/runs/labelled", response_model=list[EvalRun])
async def runs_labelled(label: str, member: CurrentMember, ledger: LedgerDep) -> list[EvalRun]:
    return ledger.with_label(label)


# --- questions about a member's own runs, answered through the copilot ---------

_CONDITION_PROMPT = (f"Rewrite the question as a single SQLite boolean expression over the eval_runs "
                     f"columns ({RUN_COLUMNS}). Reply with the expression only.")
_FIELD_PROMPT = "Rewrite the question as `name=<value>` or `label=<value>`. Reply with that line only."


@router.post("/runs/question")
async def question_runs(body: RunQuestion, member: CurrentMember, ledger: LedgerDep, copilot: CopilotDep) -> list[dict]:
    condition = await run_in_threadpool(copilot.reply, _CONDITION_PROMPT, body.question)
    return ledger.where(member.id, condition or "1=1")


@router.post("/runs/question-by-field")
async def question_runs_by_field(body: RunQuestion, member: CurrentMember, ledger: LedgerDep,
                            copilot: CopilotDep) -> list[dict]:
    answer = await run_in_threadpool(copilot.reply, _FIELD_PROMPT, body.question)
    field, _, value = answer.partition("=")
    try:
        wanted = FieldFilter(field=field.strip(), value=value.strip())
    except ValidationError:
        return []
    return ledger.by_field(member.id, wanted)


@router.post("/runs/{run_id}/verdicts", response_model=Verdict, status_code=status.HTTP_201_CREATED)
async def record_verdict(run: OwnedRun, body: VerdictBody, ledger: LedgerDep) -> Verdict:
    return ledger.record(run, body.sample, body.score, body.rationale)


@router.get("/verdicts/{verdict_id}", response_model=Verdict)
async def verdict(verdict_id: int, member: CurrentMember, ledger: LedgerDep) -> Verdict:
    found = ledger.verdict(verdict_id)
    if found is None:
        raise _missing("verdict")
    return found


@router.get("/runs/{run_id}/verdicts/{verdict_id}", response_model=Verdict)
async def run_verdict(
    run: Annotated[EvalRun, Depends(listed_run)], verdict_id: int, member: CurrentMember, ledger: LedgerDep,
) -> Verdict:
    found = ledger.verdict(verdict_id)
    if found is None:
        raise _missing("verdict")
    return found


@router.get("/runs/{run_id}/verdicts/{verdict_id}/rationale", response_model=Verdict)
async def verdict_rationale(run: OwnedRun, verdict_id: int, ledger: LedgerDep) -> Verdict:
    found = ledger.verdict_in_run(verdict_id, run.id)
    if found is None:
        raise _missing("verdict")
    return found


@router.get("/runs/{run_id}/verdicts/{verdict_id}/score", response_model=Verdict)
async def verdict_score(run: OwnedRun, verdict_id: int, ledger: LedgerDep) -> Verdict:
    found = ledger.verdicts_of(run).get(verdict_id)
    if found is None:
        raise _missing("verdict")
    return found


# --- run outputs ------------------------------------------------------------------

@router.put("/runs/{run_id}/outputs", status_code=status.HTTP_204_NO_CONTENT)
async def point_outputs(run: OwnedRun, body: OutputsBody, conn: DbDep) -> None:
    """Record the directory the run's runner writes intermediate files to."""
    set_outputs(conn, run.id, body.directory)


@router.post("/runs/{run_id}/prune", status_code=status.HTTP_202_ACCEPTED)
async def queue_prune(run: OwnedRun, body: PruneBody, member: CurrentMember, conn: DbDep) -> dict:
    """Queue removal of leftover files matching ``pattern`` from the run's outputs directory."""
    return {"queued": schedule(conn, "run.prune", {"run_id": run.id, "pattern": body.pattern}, member.id)}


# --- files written by `larchway export` and the nightly snapshot job ----------------

@router.get("/exports")
async def export_file(name: Annotated[str, Query()], member: CurrentMember, shelf: ExportShelf) -> FileResponse:
    return serve(shelf, name)


@router.get("/snapshots")
async def snapshot_file(name: Annotated[str, Query()], member: CurrentMember, shelf: SnapshotShelf) -> FileResponse:
    return serve(shelf, name)
