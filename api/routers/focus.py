"""
GET /api/focus/state -- poll-driven snapshot of the browser-drivable focus
session (focus_session_manager.manager). Always calls manager.tick() first
(then manager.snapshot() as a separate call -- see focus_session_manager.
FocusSessionManager.tick's docstring on why: threading.Lock isn't
reentrant, so tick() can't be called from inside a locked snapshot()), so
a client polling this endpoint sees an auto-completed/auto-failed session
the moment it's due, not up to a full background-loop tick late.

POST /api/focus/start, /pause, /resume, /stop -- thin wrappers around the
manager's own methods; a ValueError from the manager (wrong-state
transition, e.g. pausing an idle session) becomes an HTTP 409, matching
this project's existing precedent of surfacing a domain ValueError as an
HTTP 4xx with the exception's own message as `detail` (see character.py's
rest_character -- 400 there since that's a validation failure, 409 here
since it's specifically a state-conflict).
"""
import time

from fastapi import APIRouter, Depends, HTTPException

from procrastination_tool import auth, focus_session_manager
from procrastination_tool.focus_session_manager import FocusSessionState, manager

from ..deps import get_current_user
from ..schemas import FocusStartRequest, FocusStateOut, SessionResultOut

router = APIRouter(prefix="/focus", tags=["focus"])


def _build_focus_state_out(state: FocusSessionState) -> FocusStateOut:
    remaining_seconds = None
    paused_seconds = None
    pause_auto_fail_in_seconds = None

    if state.status == "running":
        worked = state.worked_seconds
        if state.running_since is not None:
            worked += time.monotonic() - state.running_since
        remaining_seconds = max(0.0, state.duration_minutes * 60 - worked)
    elif state.status == "paused":
        paused_seconds = time.monotonic() - state.paused_since if state.paused_since else 0.0
        pause_auto_fail_in_seconds = max(
            0.0, focus_session_manager.PAUSE_FAIL_MINUTES * 60 - paused_seconds
        )

    last_result = None
    if state.last_result is not None:
        last_result = SessionResultOut(**vars(state.last_result))

    return FocusStateOut(
        status=state.status,
        task_label=state.task_label,
        priority=state.priority,
        specific_project=state.specific_project,
        duration_minutes=state.duration_minutes if state.status != "idle" else None,
        remaining_seconds=remaining_seconds,
        paused_seconds=paused_seconds,
        pause_auto_fail_in_seconds=pause_auto_fail_in_seconds,
        last_result=last_result,
        hardcore=state.hardcore,
    )


@router.get("/state", response_model=FocusStateOut)
def get_focus_state(user: auth.User = Depends(get_current_user)) -> FocusStateOut:
    manager.tick(user.id)
    return _build_focus_state_out(manager.snapshot(user.id))


@router.post("/start", response_model=FocusStateOut)
def start_focus_session(
    body: FocusStartRequest, user: auth.User = Depends(get_current_user)
) -> FocusStateOut:
    try:
        state = manager.start(
            user_id=user.id,
            duration_minutes=body.duration_minutes,
            task_label=body.task_label,
            priority=body.priority,
            specific_project=body.specific_project,
            hardcore=body.hardcore,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_focus_state_out(state)


@router.post("/pause", response_model=FocusStateOut)
def pause_focus_session(user: auth.User = Depends(get_current_user)) -> FocusStateOut:
    try:
        state = manager.pause(user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_focus_state_out(state)


@router.post("/resume", response_model=FocusStateOut)
def resume_focus_session(user: auth.User = Depends(get_current_user)) -> FocusStateOut:
    try:
        state = manager.resume(user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_focus_state_out(state)


@router.post("/stop", response_model=FocusStateOut)
def stop_focus_session(user: auth.User = Depends(get_current_user)) -> FocusStateOut:
    try:
        manager.stop(user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_focus_state_out(manager.snapshot(user.id))
