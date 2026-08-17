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
    # Same-day follow-up: "hardcore" sessions block a real calendar event
    # (see focus_session_manager.py) -- surfaced so the frontend can show
    # an indicator on a running hardcore session.
    hardcore: bool = False


class FocusStartRequest(BaseModel):
    """Body for POST /api/focus/start."""

    duration_minutes: float
    task_label: Optional[str] = None
    priority: Optional[str] = None
    specific_project: Optional[str] = None
    hardcore: bool = False


# Web Push notifications (see procrastination_tool/push_notifications.py) --
# lets a focus-session outcome reach the user even with no tab open/focused.


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


# 2026-08-11 redesign: native task backlog (replaces Notion) + the
# proactive-nudge "Now" surface.


class BacklogTaskOut(BaseModel):
    id: int
    name: str
    priority: str
    effort_minutes: int
    notes: str
    status: str
    created_at: datetime
    specific_project: Optional[str] = None
    is_today: bool = False
    position: int = 0
    completed_at: Optional[datetime] = None
    tags: List[str] = []
    carried_forward: bool = False
    is_this_week: bool = False
    is_current_week_commitment: bool = False
    # 2026-08 page-split redesign: optional link to a Project this task is a
    # breakdown step of -- see ProjectOut below and procrastination_tool.projects.
    project_id: Optional[int] = None
    # Draft-stage Roadmap breakdown steps: True until explicitly released to
    # the Task Pool via PATCH is_draft=False.
    is_draft: bool = False


class BacklogTodayStatusOut(BaseModel):
    """Body for GET /api/backlog/today-status -- the morning check-in
    banner's only data source (counterpart to evaluation's today-status)."""

    date: date
    has_today_tasks: bool


class BacklogTaskCreateRequest(BaseModel):
    name: str
    priority: str
    notes: str = ""
    specific_project: Optional[str] = None
    tags: List[str] = []
    project_id: Optional[int] = None
    is_draft: bool = False


class BacklogTaskUpdateRequest(BaseModel):
    """Body for PATCH /api/backlog/{id} -- the Board's generic partial
    update (status change, quadrant move, Today/Pool toggle, reorder,
    notes/tags edit). Every field is optional; only fields explicitly set
    are changed (see procrastination_tool.tasks.update_task). `tags`, if
    present, REPLACES the task's full tag set (not a merge) -- the
    frontend always sends the complete desired list. `project_id` can't be
    cleared with `null` (indistinguishable from "field omitted" once this
    reaches an Optional Python param) -- send `0` to unlink, matching
    tasks.update_task's own documented sentinel."""

    name: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    specific_project: Optional[str] = None
    is_today: Optional[bool] = None
    position: Optional[int] = None
    tags: Optional[List[str]] = None
    is_this_week: Optional[bool] = None
    project_id: Optional[int] = None
    is_draft: Optional[bool] = None


# 2026-08 page-split redesign: Project tracking (procrastination_tool.projects)
# -- a standalone entity for work spanning more than one task, distinct from
# the tag Project/sub-project hierarchy below (TagOut/TagCreateRequest).


class ProjectOut(BaseModel):
    id: int
    name: str
    status: str
    notes: str
    created_at: datetime
    tags: List[str] = []


class ProjectCreateRequest(BaseModel):
    name: str
    notes: str = ""
    tags: List[str] = []


class ProjectUpdateRequest(BaseModel):
    """Body for PATCH /api/projects/{id} -- partial update, only fields
    explicitly set are changed (see procrastination_tool.projects.update_project).
    `tags`, if present, REPLACES the project's full tag set (not a merge)."""

    name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


# Fourth same-day follow-up: two-level tag hierarchy (Project / sub-project).


class TagOut(BaseModel):
    name: str
    parent: Optional[str] = None  # None means this tag IS a top-level Project


class TagCreateRequest(BaseModel):
    """Body for POST /api/tags -- create a tag (or, if it already exists,
    set/replace its parent). `parent`, if given, must itself already be
    (or become) a top-level tag -- see tasks.set_tag_parent."""

    name: str
    parent: Optional[str] = None


# Same-day follow-up: end-of-day evaluation + mood tracker (3/3.1/3.2).


class MoodEntryOut(BaseModel):
    id: int
    ts: datetime
    mood_score: int
    note: str


class MoodCreateRequest(BaseModel):
    """Body for POST /api/mood."""

    mood_score: int
    note: str = ""


class DailyEvaluationOut(BaseModel):
    date: date
    generated_at: datetime
    sessions_count: int
    focused_minutes: float
    completion_rate: Optional[float]
    tasks_completed_count: int
    runes_earned: int
    mood_avg: Optional[float]
    mood_entries: List[MoodEntryOut]
    tasks_completed_names: List[str]
    quadrant_breakdown: Dict[str, int]


class EvaluationGenerateRequest(BaseModel):
    """Body for POST /api/evaluation/generate. `date` defaults to today
    (server-side) when omitted."""

    date: Optional[date] = None


class EvaluationTodayStatusOut(BaseModel):
    """Body for GET /api/evaluation/today-status -- the end-of-day reminder
    banner's only data source. Two separate booleans rather than one
    collapsed "needs_reminder" so the frontend owns reminder policy (timing,
    dismissal), not the backend."""

    date: date
    mood_logged: bool
    evaluation_generated: bool


class WeeklyRetroOut(BaseModel):
    week_start: date
    week_end: date
    generated_at: datetime
    sessions_count: int
    focused_minutes: float
    tasks_completed_count: int
    committed_count: int
    committed_completed_count: int
    mood_avg: Optional[float]
    tasks_completed_names: List[str]
    quadrant_breakdown: Dict[str, int]


class WeeklyRetroGenerateRequest(BaseModel):
    """Body for POST /api/retro/generate. `week_start` defaults to the
    current week (server-side) when omitted; any date within the target
    week is accepted, not just the Monday itself."""

    week_start: Optional[date] = None


class PMSuggestedActionOut(BaseModel):
    """A subset of BacklogTaskUpdateRequest's fields -- "applying" a
    suggestion in the frontend is just PATCHing /api/backlog/{task_id}
    with exactly this dict, the same call the Board itself makes."""

    priority: Optional[str] = None
    is_today: Optional[bool] = None
    is_this_week: Optional[bool] = None


class PMSuggestionOut(BaseModel):
    id: str
    kind: str
    task_id: Optional[int]
    title: str
    rationale: str
    suggested_action: Optional[PMSuggestedActionOut] = None


class PMReviewOut(BaseModel):
    generated_at: datetime
    model_used: str
    suggestions: List[PMSuggestionOut]


class StandupGenerateRequest(BaseModel):
    blockers: str = ""


class StandupOut(BaseModel):
    generated_at: datetime
    model_used: str
    note_date: date
    note: str


class NowOut(BaseModel):
    """GET /api/now's response -- a snapshot of proactive_scheduler's
    persisted nudge state plus the task it refers to, or status="idle" with
    task=None if there's nothing currently nudged (either outside the cue
    window, a session is already running, or the backlog is empty)."""

    status: str  # "idle" | "pending_start"
    task: Optional[BacklogTaskOut] = None
    auto_start_in_seconds: Optional[float] = None
    swap_count: int = 0
    max_swaps: int = 0
    # Phase 3: the task's actual binding deadline (engagement, not
    # completion -- see deadlines.py) -- distinct from
    # auto_start_in_seconds, which is just the nudge's own grace countdown.
    deadline_at: Optional[datetime] = None
