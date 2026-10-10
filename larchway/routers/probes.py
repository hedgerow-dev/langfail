"""Probe a checkpoint: grade samples, pin tuning rows, read loss diagnostics."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..deps.identity import CurrentMember
from ..deps.sessions import HeadDep, VaultDep
from ..domain.probes import OUTCOMES, Reading
from ..schemas.probes import Classification, EvalSet, GradedSample, LossOut, SampleBody

router = APIRouter(prefix="/v1/probes", tags=["probes"])


def known_outcome(body: GradedSample | EvalSet) -> str:
    if body.outcome not in OUTCOMES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown outcome")
    return body.outcome


@router.post("/{checkpoint_id}/read", response_model=Reading)
async def read_sample(checkpoint_id: int, body: SampleBody, member: CurrentMember, head: HeadDep) -> Reading:
    """Grade a sample and show the head's confidence in every outcome."""
    return head.read(body.sample)


@router.post("/{checkpoint_id}/classify", response_model=Classification)
async def classify_sample(checkpoint_id: int, body: SampleBody, member: CurrentMember,
                          head: HeadDep) -> Reading:
    return head.read(body.sample)


@router.post("/{checkpoint_id}/tuning-rows", status_code=status.HTTP_204_NO_CONTENT)
async def pin_tuning_row(checkpoint_id: int, body: GradedSample, member: CurrentMember, vault: VaultDep,
                         head: HeadDep) -> None:
    if vault.find(checkpoint_id).member_id != member.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such checkpoint")
    head.pin(body.sample, known_outcome(body))


@router.post("/{checkpoint_id}/sample-loss", response_model=LossOut)
async def sample_loss(checkpoint_id: int, body: GradedSample, member: CurrentMember, head: HeadDep) -> LossOut:
    return LossOut(checkpoint_id=checkpoint_id, cross_entropy=head.loss_of(body.sample, known_outcome(body)))


@router.post("/{checkpoint_id}/eval-loss", response_model=LossOut)
async def eval_set_loss(checkpoint_id: int, body: EvalSet, member: CurrentMember, head: HeadDep) -> LossOut:
    return LossOut(checkpoint_id=checkpoint_id, cross_entropy=head.pooled_loss(body.samples, known_outcome(body)))
