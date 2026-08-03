"""
Phase 1 core spine, extracted into the package so both `scripts/sync_tasks.py`
(the LaunchAgent-driven daily automation) and `app.py` (Phase 4's dashboard
"manual sync" button) call the exact same code -- no logic duplicated
between the two, per the Phase 4 plan's own requirement.

Idempotent by design: each created event's notes are tagged with
`notion_id:<page_id>` (plus `Priority:`/`Due:` -- see _build_notes/
_parse_notes below), and every task is checked against
calendar_bridge.find_event_by_notion_id() *before* scheduling -- a task
that already has a block is skipped, not duplicated.

Reconciliation (added 2026-08-02, replacing an earlier bounded-lookback
"find recently completed pages" approach after it turned out not to catch
the user's real case -- they *edited* a task's name/priority/date rather
than completing or deleting it): every run first walks every existing
calendar block, looks up its tagged page's *current* live state directly
by ID (notion_tasks.get_live_task_snapshot), and removes the block if the
task is gone/archived/no-longer-actionable OR if its name, priority, or
due date has drifted from what's stored in the block's own notes. A
removed block's task is then naturally rescheduled fresh (correct name/
duration/date) by the normal scheduling pass below, since it no longer
has a matching block. This is a full reconciliation against Notion's
current truth, not a bounded query for one kind of change (e.g. only
"was it completed in the last N days") -- it catches every way a task can
stop matching what its block says, including edits and deletions that a
status-filtered query can never see (a deleted page simply doesn't appear
in any query result at all).
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import calendar_bridge, notion_tasks, scheduler
from .calendar_bridge import CalendarEvent
from .notion_tasks import Task
from .scheduler import Placement


@dataclass
class SyncResult:
    created: List[Placement] = field(default_factory=list)
    already_blocked: List[Task] = field(default_factory=list)
    unscheduled: List[Task] = field(default_factory=list)
    removed_count: int = 0


def _build_notes(task: Task) -> str:
    return f"notion_id:{task.page_id}\nPriority: {task.priority}\nDue: {task.due.isoformat()}\n{task.url}"


def _parse_notes(notes: str) -> dict:
    parsed = {"notion_id": None, "priority": None, "due": None}
    for line in notes.splitlines():
        if line.startswith("notion_id:"):
            parsed["notion_id"] = line[len("notion_id:"):].strip()
        elif line.startswith("Priority:"):
            val = line[len("Priority:"):].strip()
            parsed["priority"] = val if val and val != "None" else None
        elif line.startswith("Due:"):
            parsed["due"] = line[len("Due:"):].strip()
    return parsed


def _reconcile_calendar_with_notion(log_fn: Callable[[str], None]) -> int:
    removed = 0
    for ev in calendar_bridge.list_all_events(calendar_bridge.FOCUS_CALENDAR_NAME):
        tag = _parse_notes(ev.notes)
        page_id = tag["notion_id"]
        if not page_id:
            continue  # not one of ours -- shouldn't happen in this calendar, but don't touch what we didn't tag

        live = notion_tasks.get_live_task_snapshot(page_id)
        reason: Optional[str] = None
        if live is None:
            reason = "task no longer exists / archived / not actionable (done, discarded, or missing priority/date)"
        elif live.name != ev.summary:
            reason = f"name changed ({ev.summary!r} -> {live.name!r})"
        elif tag["priority"] != live.priority:
            reason = f"priority changed ({tag['priority']} -> {live.priority})"
        elif tag["due"] != live.due.isoformat():
            reason = f"due date changed ({tag['due']} -> {live.due.isoformat()})"

        if reason:
            calendar_bridge.delete_event_by_uid(ev.uid)
            removed += 1
            log_fn(f"Removed stale block for {ev.summary!r}: {reason}")

    return removed


def run_sync(log_fn: Callable[[str], None] = lambda msg: None) -> SyncResult:
    # Reconciliation runs first, unconditionally -- a task refreshed here
    # (drifted name/priority/due) needs its old block gone *before* the
    # idempotency check below, so it gets picked up as "needs scheduling"
    # in the same run rather than staying stale until the next one.
    removed_count = _reconcile_calendar_with_notion(log_fn)
    if removed_count:
        log_fn(f"Removed {removed_count} stale/completed calendar block(s)")

    all_tasks = notion_tasks.fetch_actionable_tasks()
    log_fn(f"Fetched {len(all_tasks)} actionable task(s) from Notion")

    # Idempotency check happens BEFORE scheduling, not after -- an
    # already-blocked task shouldn't consume a calendar slot in this run's
    # free-slot computation at all.
    already_blocked: List[Task] = []
    to_schedule: List[Task] = []
    for task in all_tasks:
        existing_uid = calendar_bridge.find_event_by_notion_id(task.page_id)
        if existing_uid:
            already_blocked.append(task)
        else:
            to_schedule.append(task)

    log_fn(f"{len(already_blocked)} task(s) already have a block (skipped), "
           f"{len(to_schedule)} to schedule this run")

    if not to_schedule:
        return SyncResult(created=[], already_blocked=already_blocked, unscheduled=[], removed_count=removed_count)

    placements, unscheduled = scheduler.schedule_tasks(to_schedule)

    created: List[Placement] = []
    for p in placements:
        uid = calendar_bridge.create_event(p.task.name, p.start, p.end, notes=_build_notes(p.task))
        log_fn(f"Created block for {p.task.name!r} "
               f"{p.start.strftime('%a %Y-%m-%d %H:%M')}-{p.end.strftime('%H:%M')} (uid={uid})")
        created.append(p)

    if unscheduled:
        log_fn(f"WARNING: {len(unscheduled)} task(s) could not be fit into the scheduling horizon")

    return SyncResult(created=created, already_blocked=already_blocked, unscheduled=unscheduled, removed_count=removed_count)
