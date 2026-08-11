"""
Deadline + effort-tracking engine (2026-08-11 redesign, Phase 3).

A deadline governs ENGAGEMENT, not completion: it's satisfied once the user
starts and substantially works a focus session on the task by the deadline
time -- not by the task itself getting marked done. Someone who genuinely
worked a full session on a task too big/hard to finish in one sitting
shouldn't be treated the same as someone who never engaged with it at all
(see the redesign plan's Part 1 for why -- this was a direct correction from
the user during the brainstorm, not an assumption). If a session is
genuinely worked but the task isn't finished, this module doesn't penalize
it -- the next tick's ensure_deadlines() just gives it a fresh deadline for
the next chunk, once its current one resolves.

No consequence engine exists yet (that's Phase 5's stakes/email pipeline)
-- this module only tracks status (pending/engaged/missed/passed) and logs
to stake_events, the same audit table the eventual stakes engine will read
pass-usage from (kept here rather than a separate passes.py for now, since
"a pass" is currently just "flip this one deadline to passed" -- split out
if/when Phase 5's rate-limiting needs grow past that).
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from . import tasks as tasks_module
from .config import (
    DEADLINE_HORIZON_HOURS_BY_PRIORITY,
    DEFAULT_GRACE_MINUTES,
    EFFORT_CREDIT_RATIO,
    SESSION_DB_PATH,
    WEEKLY_PASS_LIMIT,
)

STATUS_PENDING = "pending"
STATUS_ENGAGED = "engaged"
STATUS_MISSED = "missed"
STATUS_PASSED = "passed"

_SCHEMA_DEADLINES = """
CREATE TABLE IF NOT EXISTS task_deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    deadline_at TEXT NOT NULL,
    grace_minutes INTEGER NOT NULL DEFAULT 15,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

# Shared audit log -- Phase 5's stake_engine will extend this with
# pool_item_id/recipient_id columns (lazy ALTER TABLE, same pattern
# focus_timer.py uses) once those concepts exist. For now it only ever logs
# deadline_missed/pass_used/completed_before_deadline.
_SCHEMA_EVENTS = """
CREATE TABLE IF NOT EXISTS stake_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    deadline_id INTEGER,
    detail TEXT
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute(_SCHEMA_DEADLINES)
    conn.execute(_SCHEMA_EVENTS)
    return conn


@dataclass
class Deadline:
    id: int
    task_id: int
    deadline_at: datetime
    grace_minutes: int
    status: str
    created_at: datetime
    updated_at: datetime


def _row_to_deadline(row: sqlite3.Row) -> Deadline:
    return Deadline(
        id=row["id"], task_id=row["task_id"], deadline_at=datetime.fromisoformat(row["deadline_at"]),
        grace_minutes=row["grace_minutes"], status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _log_event(conn: sqlite3.Connection, event_type: str, deadline_id: Optional[int] = None,
               detail: Optional[str] = None, ts: Optional[datetime] = None) -> None:
    conn.execute(
        "INSERT INTO stake_events (ts, event_type, deadline_id, detail) VALUES (?, ?, ?, ?)",
        ((ts or datetime.now()).isoformat(), event_type, deadline_id, detail),
    )


def get_active_deadline(task_id: int) -> Optional[Deadline]:
    """The task's current *pending* deadline, if any -- a task can cycle
    through multiple deadlines over its life (one per attempted chunk), but
    only ever has one pending at a time."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM task_deadlines WHERE task_id = ? AND status = ? ORDER BY id DESC LIMIT 1",
            (task_id, STATUS_PENDING),
        ).fetchone()
    return _row_to_deadline(row) if row else None


def get_deadline(deadline_id: int) -> Optional[Deadline]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_deadlines WHERE id = ?", (deadline_id,)).fetchone()
    return _row_to_deadline(row) if row else None


def assign_deadline(task: tasks_module.Task, now: Optional[datetime] = None) -> Deadline:
    now = now or datetime.now()
    horizon_hours = DEADLINE_HORIZON_HOURS_BY_PRIORITY.get(task.priority, 24)
    deadline_at = now + timedelta(hours=horizon_hours)
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO task_deadlines (task_id, deadline_at, grace_minutes, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task.id, deadline_at.isoformat(), DEFAULT_GRACE_MINUTES, STATUS_PENDING,
             now.isoformat(), now.isoformat()),
        )
        conn.commit()
        deadline_id = cur.lastrowid
    return Deadline(id=deadline_id, task_id=task.id, deadline_at=deadline_at,
                     grace_minutes=DEFAULT_GRACE_MINUTES, status=STATUS_PENDING, created_at=now, updated_at=now)


def ensure_deadlines(actionable_tasks: List[tasks_module.Task]) -> None:
    """Called every tick -- every actionable task should have exactly one
    pending deadline. No-op for a task that already has one (including one
    freshly re-issued after its last one resolved as engaged/passed --
    engagement doesn't retire a task, just its current deadline)."""
    for task in actionable_tasks:
        if get_active_deadline(task.id) is None:
            assign_deadline(task)


def sweep_missed(now: Optional[datetime] = None) -> int:
    """Any pending deadline whose grace window has fully elapsed with no
    qualifying session flips to 'missed' -- logged for the future stakes
    engine to act on, but Phase 3 has no consequence yet. Returns the count
    swept, mainly for tests/smoke-checks."""
    now = now or datetime.now()
    swept = 0
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM task_deadlines WHERE status = ?", (STATUS_PENDING,)).fetchall()
        for row in rows:
            d = _row_to_deadline(row)
            if now >= d.deadline_at + timedelta(minutes=d.grace_minutes):
                conn.execute(
                    "UPDATE task_deadlines SET status = ?, updated_at = ? WHERE id = ?",
                    (STATUS_MISSED, now.isoformat(), d.id),
                )
                _log_event(conn, "deadline_missed", deadline_id=d.id, ts=now)
                swept += 1
        conn.commit()
    return swept


def record_session_outcome(task_id: Optional[int], actual_minutes: float, planned_minutes: float) -> bool:
    """Called once a tracked session (started via the Now flow for a known
    task_id) ends, regardless of outcome (completed/stopped_early/failed_
    pause_timeout all go through this the same way -- only the worked
    fraction matters). Returns True if this counted as engagement."""
    if task_id is None or planned_minutes <= 0:
        return False
    deadline = get_active_deadline(task_id)
    if deadline is None:
        return False
    engaged = (actual_minutes / planned_minutes) >= EFFORT_CREDIT_RATIO
    if engaged:
        with closing(_connect()) as conn:
            conn.execute(
                "UPDATE task_deadlines SET status = ?, updated_at = ? WHERE id = ?",
                (STATUS_ENGAGED, datetime.now().isoformat(), deadline.id),
            )
            _log_event(conn, "completed_before_deadline", deadline_id=deadline.id)
            conn.commit()
    # Not engaged (stopped very early): leave the deadline pending as-is --
    # there's still time to genuinely try again before its own deadline+
    # grace lapses.
    return engaged


def _week_start(now: datetime) -> datetime:
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def passes_remaining_this_week(now: Optional[datetime] = None) -> int:
    now = now or datetime.now()
    with closing(_connect()) as conn:
        used = conn.execute(
            "SELECT COUNT(*) FROM stake_events WHERE event_type = ? AND ts >= ?",
            ("pass_used", _week_start(now).isoformat()),
        ).fetchone()[0]
    return max(0, WEEKLY_PASS_LIMIT - used)


class NoPassesRemainingError(ValueError):
    pass


def use_pass(deadline_id: int, now: Optional[datetime] = None) -> None:
    """No-questions-asked skip for one specific pending deadline -- caps at
    WEEKLY_PASS_LIMIT (default 1/week) via the audit log, not a separate
    counter, so it's always derivable/auditable from stake_events alone."""
    now = now or datetime.now()
    with closing(_connect()) as conn:
        row = conn.execute("SELECT status FROM task_deadlines WHERE id = ?", (deadline_id,)).fetchone()
        if row is None:
            raise ValueError("Deadline not found")
        if row[0] != STATUS_PENDING:
            raise ValueError(f"Deadline is already {row[0]}, not pending")
        used = conn.execute(
            "SELECT COUNT(*) FROM stake_events WHERE event_type = ? AND ts >= ?",
            ("pass_used", _week_start(now).isoformat()),
        ).fetchone()[0]
        if used >= WEEKLY_PASS_LIMIT:
            raise NoPassesRemainingError("No passes remaining this week")
        conn.execute(
            "UPDATE task_deadlines SET status = ?, updated_at = ? WHERE id = ?",
            (STATUS_PASSED, now.isoformat(), deadline_id),
        )
        _log_event(conn, "pass_used", deadline_id=deadline_id, ts=now)
        conn.commit()
