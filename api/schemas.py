"""
Pydantic response/request models for the API surface.

These mirror the NamedTuples/dataclasses/sqlite Row shapes returned by the
`procrastination_tool` package (see notion_tasks.Task, calendar_bridge.
CalendarEvent, block_grid.Row/RowState, focus_timer.SessionRow, character.
Character, bloodstain.Bloodstain, questlines' sqlite Row, gear.GearItem) --
kept in sync by hand, no codegen at this size (per the migration plan).

Phase 3 adds the first request body model (StatRestRequest) alongside the
Phase 1 response-only models, for the new POST /character/rest and
POST /gear/{gear_id}/buy write endpoints.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class TaskOut(BaseModel):
    page_id: str
    name: str
    priority: Optional[str]
    start_date: date
    notes: str
    url: str
    specific_project: Optional[str] = None
    # Phase 4: how many Focus-Blocks-calendar events (any day) are already
    # tagged with this task's page_id -- see block_grid.count_assigned_instances.
    # Drives the frontend's "how many more instance boxes of this task
    # should show up in the pool" computation (1 + extra - assigned_count).
    assigned_count: int = 0


class WeekRangeOut(BaseModel):
    today: date
    week_end: date
    days: List[date]


class CalendarEventOut(BaseModel):
    uid: str
    summary: str
    start: datetime
    end: datetime
    notes: str


class RowOut(BaseModel):
    start: datetime
    work_end: datetime
    break_end: datetime


class RowStateOut(BaseModel):
    row: RowOut
    status: str  # "empty" | "assigned" | "busy"
    event: Optional[CalendarEventOut] = None
    busy_summary: Optional[str] = None


class GridOut(BaseModel):
    day: date
    check_conflicts: bool
    rows: List[RowStateOut]


class SessionOut(BaseModel):
    id: int
    start_time: datetime
    end_time: datetime
    planned_minutes: float
    actual_minutes: float
    completed: bool
    task_label: Optional[str]
    wheel_result: Optional[str]
    outcome: Optional[str]
    runes_awarded: int
    specific_project: Optional[str]


class StatsOut(BaseModel):
    sessions: int
    completion_rate: Optional[float]
    focused_minutes: float
    daily_minutes: Dict[str, float]


class CharacterOut(BaseModel):
    runes: int
    level: int
    stats: Dict[str, int]
    next_costs: Dict[str, int]


class BloodstainOut(BaseModel):
    id: int
    runes: int
    created_at: datetime
    session_id: Optional[int]


class QuestlineOut(BaseModel):
    project_name: str
    session_count: int
    milestones_paid: int


class GearOut(BaseModel):
    gear_id: str
    name: str
    cost: int
    min_level: int
    flavor_text: str
    owned: bool
    can_buy: bool


class StatRestRequest(BaseModel):
    """Body for POST /api/character/rest -- bonfire leveling."""

    stat_name: str


class AssignedEventOut(BaseModel):
    """Same shape as CalendarEventOut -- kept as a distinct model (rather
    than reusing CalendarEventOut directly) since it's the response of a
    real Calendar.app WRITE (assign/move), not a read, and may grow
    write-specific fields later."""

    uid: str
    summary: str
    start: datetime
    end: datetime
    notes: str


class AssignRequest(BaseModel):
    """Body for POST /api/planner/assign -- drag a pool task onto an empty
    row. `row_start`/`row_end` are server-validated against
    block_grid.generate_day_rows(day) before any write happens (defense
    against a stale/tampered client) -- row_end corresponds to the row's
    work_end (the 45-min work portion only, not the trailing break)."""

    page_id: str
    day: date
    row_start: datetime
    row_end: datetime


class MoveRequest(BaseModel):
    """Body for POST /api/planner/move -- drag an already-assigned event
    (identified by its Calendar.app uid) to a different row."""

    uid: str
    day: date
    row_start: datetime
    row_end: datetime


class DeleteAssignOut(BaseModel):
    deleted: bool


class PlannerRefreshOut(BaseModel):
    removed_count: int
    log: List[str]


class CompleteTaskOut(BaseModel):
    removed_blocks: int


# Phase 5: browser-drivable focus timer (focus_session_manager.FocusSessionManager).


class SessionResultOut(BaseModel):
    """Mirrors focus_timer.SessionResult -- the outcome of a just-finished
    session, surfaced on FocusStateOut.last_result until the next start()."""

    completed: bool
    actual_minutes: float
    wheel_result: Optional[str]
    outcome: str
    runes_awarded: int


class FocusStateOut(BaseModel):
    """GET /api/focus/state's response -- a snapshot of
    focus_session_manager.FocusSessionState plus the computed fields a
    client needs to render a countdown/pause banner without doing its own
    monotonic-time math (it only has wall-clock Date.now(), and the
    server's time.monotonic() base isn't meaningful to it anyway).

    remaining_seconds is set only while status == "running"; paused_seconds/
    pause_auto_fail_in_seconds only while status == "paused" -- the other
    pair is None in either case, rather than a stale/zero value, so the
    frontend can branch on presence instead of on `status` twice."""

    status: str  # "idle" | "running" | "paused"
    task_label: Optional[str] = None
    priority: Optional[str] = None
    specific_project: Optional[str] = None
    duration_minutes: Optional[float] = None
    remaining_seconds: Optional[float] = None
    paused_seconds: Optional[float] = None
    pause_auto_fail_in_seconds: Optional[float] = None
    last_result: Optional[SessionResultOut] = None


class FocusStartRequest(BaseModel):
    """Body for POST /api/focus/start."""

    duration_minutes: float
    task_label: Optional[str] = None
    priority: Optional[str] = None
    specific_project: Optional[str] = None
