"""
The proactive "Now" surface (2026-08-11 redesign) -- GET /api/now polls
proactive_scheduler's persisted nudge state (the same state its own
background tick, registered in api/main.py's lifespan, advances every
second). POST /now/start and /now/swap are thin wrappers around the
scheduler's own functions, matching this project's existing precedent
(focus.py) of surfacing a domain ValueError as an HTTP 409.
"""
from fastapi import APIRouter, HTTPException

from procrastination_tool import proactive_scheduler

from ..schemas import BacklogTaskOut, NowOut

router = APIRouter(prefix="/now", tags=["now"])


def _build_now_out(snap: proactive_scheduler.NowSnapshot) -> NowOut:
    task_out = BacklogTaskOut(**vars(snap.task)) if snap.task else None
    return NowOut(
        status=snap.status, task=task_out, auto_start_in_seconds=snap.auto_start_in_seconds,
        swap_count=snap.swap_count, max_swaps=snap.max_swaps, deadline_at=snap.deadline_at,
    )


@router.get("", response_model=NowOut)
def get_now() -> NowOut:
    return _build_now_out(proactive_scheduler.snapshot())


@router.post("/start", response_model=NowOut)
def start_now() -> NowOut:
    try:
        proactive_scheduler.start_now()
    except proactive_scheduler.NoCandidateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_now_out(proactive_scheduler.snapshot())


@router.post("/swap", response_model=NowOut)
def swap_now() -> NowOut:
    try:
        proactive_scheduler.swap()
    except proactive_scheduler.NoCandidateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_now_out(proactive_scheduler.snapshot())
