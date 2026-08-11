"""
Proactive nudge engine (2026-08-11 redesign) -- the paradigm-shift module.

The rest of this app is deliberately pull-based: every existing feature
waits for the user to open it. This module inverts that for task
selection: during working hours, if nothing is currently running, it
auto-picks the top-ranked actionable task, fires a desktop notification for
it, and -- unless the user taps Start or Swap first -- auto-starts a focus
session on it once a short grace window elapses. The user never has to
browse a task list to begin working; browsing (via Swap) is available but
capped, so "pick something else" can't turn back into open-ended choice.

State is persisted in nudge_state (not held in memory like
focus_session_manager's singleton) because the whole point of this module is
that it must survive the backend process restarting without losing track of
"what was I about to nudge about" -- see the redesign plan's data-model note.

tick() is called once a second from api/main.py's lifespan loop, alongside
focus_session_manager.manager.tick() -- same pattern, same loop.
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from . import deadlines, notify, tasks
from .config import (
    AUTO_START_GRACE_SECONDS,
    FOCUS_SESSION_MINUTES,
    LUNCH_END_HOUR,
    LUNCH_START_HOUR,
    MAX_NUDGE_CANDIDATES,
    MAX_NUDGE_SWAPS,
    SESSION_DB_PATH,
    WORKING_WEEKDAYS,
    WORK_END_HOUR,
    WORK_START_HOUR,
)
from .focus_session_manager import manager as focus_manager

STATUS_IDLE = "idle"
STATUS_PENDING_START = "pending_start"
# A session is running that this scheduler started for current_task_id --
# distinct from "the user started something else manually while a nudge
# happened to be pending" (see tick()'s STATUS_PENDING_START branch), so
# that only sessions we know are tied to a real deadline get effort-tracked.
STATUS_STARTED = "started"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nudge_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_task_id INTEGER,
    candidate_index INTEGER NOT NULL DEFAULT 0,
    swap_count INTEGER NOT NULL DEFAULT 0,
    nudge_sent_at TEXT,
    auto_start_at TEXT,
    session_planned_minutes REAL,
    status TEXT NOT NULL DEFAULT 'idle'
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute(_SCHEMA)
    # sqlite has no ADD COLUMN IF NOT EXISTS -- guarded ALTER TABLE is this
    # project's established lazy-migration pattern (see focus_timer.py's
    # _connect()). Needed here because nudge_state already existed (Phase 1)
    # before session_planned_minutes was added (Phase 3).
    try:
        conn.execute("ALTER TABLE nudge_state ADD COLUMN session_planned_minutes REAL")
    except sqlite3.OperationalError:
        pass  # column already exists
    return conn


@dataclass
class NudgeState:
    current_task_id: Optional[int]
    candidate_index: int
    swap_count: int
    nudge_sent_at: Optional[datetime]
    auto_start_at: Optional[datetime]
    status: str
    session_planned_minutes: Optional[float] = None


def _get_state() -> NudgeState:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM nudge_state WHERE id = 1").fetchone()
    if row is None:
        return NudgeState(None, 0, 0, None, None, STATUS_IDLE, None)
    return NudgeState(
        current_task_id=row["current_task_id"],
        candidate_index=row["candidate_index"],
        swap_count=row["swap_count"],
        nudge_sent_at=datetime.fromisoformat(row["nudge_sent_at"]) if row["nudge_sent_at"] else None,
        auto_start_at=datetime.fromisoformat(row["auto_start_at"]) if row["auto_start_at"] else None,
        status=row["status"],
        session_planned_minutes=row["session_planned_minutes"],
    )


def _save_state(state: NudgeState) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO nudge_state (id, current_task_id, candidate_index, swap_count, "
            "nudge_sent_at, auto_start_at, session_planned_minutes, status) VALUES (1, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET current_task_id=excluded.current_task_id, "
            "candidate_index=excluded.candidate_index, swap_count=excluded.swap_count, "
            "nudge_sent_at=excluded.nudge_sent_at, auto_start_at=excluded.auto_start_at, "
            "session_planned_minutes=excluded.session_planned_minutes, status=excluded.status",
            (
                state.current_task_id, state.candidate_index, state.swap_count,
                state.nudge_sent_at.isoformat() if state.nudge_sent_at else None,
                state.auto_start_at.isoformat() if state.auto_start_at else None,
                state.session_planned_minutes,
                state.status,
            ),
        )
        conn.commit()


def _reset() -> None:
    _save_state(NudgeState(None, 0, 0, None, None, STATUS_IDLE, None))


def _within_cue_window(now: datetime) -> bool:
    if now.weekday() not in WORKING_WEEKDAYS:
        return False
    if LUNCH_START_HOUR <= now.hour < LUNCH_END_HOUR:
        return False
    return WORK_START_HOUR <= now.hour < WORK_END_HOUR


def _candidates() -> List[tasks.Task]:
    return tasks.list_actionable_tasks()[:MAX_NUDGE_CANDIDATES]


def _arm(candidates: List[tasks.Task], index: int, now: datetime, swap_count: int = 0) -> None:
    task = candidates[index]
    notify.send_actionable_notification(
        task.name, subtitle=f"~{task.effort_minutes} min · {task.priority.split(' (')[0]}"
    )
    _save_state(NudgeState(
        current_task_id=task.id, candidate_index=index, swap_count=swap_count,
        nudge_sent_at=now, auto_start_at=now + timedelta(seconds=AUTO_START_GRACE_SECONDS),
        status=STATUS_PENDING_START,
    ))


def tick() -> None:
    """Call periodically (background loop) alongside focus_manager.tick(),
    same pattern as api/main.py's existing lifespan task."""
    now = datetime.now()
    state = _get_state()
    snap = focus_manager.snapshot()
    session_status = snap.status

    if state.status == STATUS_STARTED:
        if session_status == STATUS_IDLE:
            # The session we started has ended (any outcome) -- record
            # whether it counted as genuine engagement against the task's
            # deadline, then stand down. snap.last_result is the manager's
            # own freshly-finalized result; snap.duration_minutes is reset
            # to None on finalize, which is exactly why the planned length
            # was persisted on nudge_state at start time instead.
            if snap.last_result is not None and state.session_planned_minutes:
                deadlines.record_session_outcome(
                    state.current_task_id, snap.last_result.actual_minutes, state.session_planned_minutes,
                )
            _reset()
        return

    if state.status == STATUS_IDLE:
        actionable = tasks.list_actionable_tasks()
        deadlines.ensure_deadlines(actionable)
        deadlines.sweep_missed(now)
        if session_status == STATUS_IDLE and _within_cue_window(now):
            candidates = actionable[:MAX_NUDGE_CANDIDATES]
            if candidates:
                _arm(candidates, index=0, now=now)
        return

    if state.status == STATUS_PENDING_START:
        if session_status != STATUS_IDLE:
            # Something else started a session while this nudge was pending
            # (e.g. a manual free-text session via FocusTimerWidget) -- we
            # can't be sure it's for the nudged task, so stand down without
            # crediting any deadline rather than guessing.
            _reset()
            return
        if now >= state.auto_start_at:
            _start_task(state.current_task_id)


def _start_task(task_id: Optional[int]) -> None:
    task = tasks.get_task(task_id) if task_id else None
    if task is None:
        _reset()
        return
    tasks.mark_in_progress(task.id)
    focus_manager.start(
        duration_minutes=FOCUS_SESSION_MINUTES, task_label=task.name,
        priority=task.priority, specific_project=None,
    )
    # Stay armed (as STATUS_STARTED, not idle) so tick() can catch the
    # session's end and record its effort outcome against the deadline --
    # see the STATUS_STARTED branch above.
    _save_state(NudgeState(
        current_task_id=task.id, candidate_index=0, swap_count=0, nudge_sent_at=None,
        auto_start_at=None, status=STATUS_STARTED, session_planned_minutes=FOCUS_SESSION_MINUTES,
    ))


class NoCandidateError(ValueError):
    pass


def start_now() -> None:
    """User-triggered immediate start of the currently nudged task,
    bypassing the remaining grace window."""
    state = _get_state()
    if state.status != STATUS_PENDING_START or state.current_task_id is None:
        raise NoCandidateError("No nudged task to start")
    _start_task(state.current_task_id)


def swap() -> NudgeState:
    """Substitute the next-ranked candidate instantly -- capped at
    MAX_NUDGE_SWAPS so this can't become open-ended browsing (the exact
    choice-paralysis pattern the redesign is trying to eliminate)."""
    state = _get_state()
    if state.status != STATUS_PENDING_START:
        raise NoCandidateError("No nudged task to swap")
    if state.swap_count >= MAX_NUDGE_SWAPS:
        return state
    candidates = _candidates()
    if len(candidates) < 2:
        return state
    next_index = (state.candidate_index + 1) % len(candidates)
    _arm(candidates, index=next_index, now=datetime.now(), swap_count=state.swap_count + 1)
    return _get_state()


def snapshot() -> "NowSnapshot":
    state = _get_state()
    # STATUS_STARTED has its own current_task_id too (a session is running
    # for it), but there's nothing for the Now view to show/act on in that
    # case -- FocusTimerWidget already renders the running session -- so it
    # surfaces here as plain "idle" rather than a third UI-facing status.
    ui_status = state.status if state.status == STATUS_PENDING_START else STATUS_IDLE
    task = tasks.get_task(state.current_task_id) if state.current_task_id and ui_status != STATUS_IDLE else None
    auto_start_in_seconds = None
    deadline_at = None
    if ui_status == STATUS_PENDING_START and state.auto_start_at:
        auto_start_in_seconds = max(0.0, (state.auto_start_at - datetime.now()).total_seconds())
    if task is not None:
        active_deadline = deadlines.get_active_deadline(task.id)
        if active_deadline is not None:
            deadline_at = active_deadline.deadline_at
    return NowSnapshot(
        status=ui_status if task else STATUS_IDLE,
        task=task,
        auto_start_in_seconds=auto_start_in_seconds,
        swap_count=state.swap_count,
        max_swaps=MAX_NUDGE_SWAPS,
        deadline_at=deadline_at,
    )


@dataclass
class NowSnapshot:
    status: str
    task: Optional[tasks.Task]
    auto_start_in_seconds: Optional[float]
    swap_count: int
    max_swaps: int
    deadline_at: Optional[datetime] = None
