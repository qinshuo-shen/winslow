"""
Manual drag-and-drop scheduling grid (2026-08-06) -- replaces the automatic
first-fit scheduler (scheduler.py, left on disk but disconnected from every
UI, same precedent as spin_wheel.py from the RPG redesign) with a fixed grid
of 45-minute work rows the user assigns tasks to by hand.

**2026-08-07**: scheduler.py was also still being triggered automatically
by a daily/on-login LaunchAgent (scripts/sync_tasks.py -> sync.run_sync() ->
scheduler.schedule_tasks()), silently competing with this grid -- that
LaunchAgent has since been unloaded (see scripts/sync_tasks.py's docstring).
sync.py's *reconciliation* half (removing stale/completed blocks) is still
live, called directly by the dashboard's "Refresh" button and by
api/routers/planner.py -- it's only the auto-placement half that's now
fully disconnected.

Deliberately NOT built on scheduler.py's stateful greedy internals -- this
module only answers "what are today's fixed row slots, and what (if
anything) already occupies each one," it does no placement/optimization
itself. Each row is BLOCK_WORK_MINUTES of work immediately followed by an
implicit BLOCK_BREAK_MINUTES break that is never its own calendar event --
same "just shows as free time" precedent as scheduler.py's break_fn. Rows
step in fixed 60-minute (45+15) increments from the start of each of the
day's existing work windows (weekday morning/afternoon, weekend), which
divides every one of them evenly with no leftover.

Calendar.app (via calendar_bridge, the project's sole write path) stays the
one source of truth for "what's assigned where" -- this module reads it to
overlay each row's live status, it never persists assignments itself.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Dict, List, NamedTuple, Optional, Tuple

from . import calendar_bridge
from .config import (
    BLOCK_BREAK_MINUTES,
    BLOCK_WORK_MINUTES,
    LUNCH_END_HOUR,
    LUNCH_START_HOUR,
    SATURDAY,
    SUNDAY,
    WEEKEND_END_HOUR,
    WEEKEND_START_HOUR,
    WORK_END_HOUR,
    WORK_START_HOUR,
    WORKING_WEEKDAYS,
)

Interval = Tuple[datetime, datetime]


class Row(NamedTuple):
    start: datetime
    work_end: datetime
    break_end: datetime


class RowState(NamedTuple):
    row: Row
    status: str  # "empty" | "assigned" | "busy"
    event: Optional[calendar_bridge.CalendarEvent] = None
    busy_summary: Optional[str] = None


def _day_windows(day: date) -> List[Interval]:
    """The day's existing work-hour windows (weekday morning/afternoon
    split around lunch, weekend single window) -- same source-of-truth
    hour constants scheduler.py uses, just read directly rather than via
    scheduler._work_blocks_for_day (which also folds in floor-clipping and
    Sunday-only logic this module doesn't need)."""
    if day.weekday() not in WORKING_WEEKDAYS:
        return []
    if day.weekday() in (SATURDAY, SUNDAY):
        return [(datetime.combine(day, time(WEEKEND_START_HOUR, 0)),
                 datetime.combine(day, time(WEEKEND_END_HOUR, 0)))]
    return [
        (datetime.combine(day, time(WORK_START_HOUR, 0)), datetime.combine(day, time(LUNCH_START_HOUR, 0))),
        (datetime.combine(day, time(LUNCH_END_HOUR, 0)), datetime.combine(day, time(WORK_END_HOUR, 0))),
    ]


def generate_day_rows(day: date) -> List[Row]:
    """Fixed 60-minute (45 work + 15 break) rows stepped from the start of
    each of the day's work windows. A row is only emitted if its full work
    portion fits before the window ends; its break is clipped to the
    window's end if the window doesn't have room for the full 15 minutes
    (doesn't happen with today's hour-aligned config, but kept correct in
    case those hours ever change)."""
    rows: List[Row] = []
    work_delta = timedelta(minutes=BLOCK_WORK_MINUTES)
    break_delta = timedelta(minutes=BLOCK_BREAK_MINUTES)

    for window_start, window_end in _day_windows(day):
        cursor = window_start
        while cursor + work_delta <= window_end:
            work_end = cursor + work_delta
            break_end = min(work_end + break_delta, window_end)
            rows.append(Row(start=cursor, work_end=work_end, break_end=break_end))
            cursor = work_end + break_delta

    return rows


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def get_row_states(
    day: date,
    assigned_events: Optional[List[calendar_bridge.CalendarEvent]] = None,
    busy_intervals: Optional[List[calendar_bridge.BusyInterval]] = None,
) -> List[RowState]:
    """Overlays each of the day's rows with its live status: 'assigned' if
    a Focus-Blocks-calendar event (this tool's own writes) already covers
    it, 'busy' if a passed-in external-calendar interval overlaps it
    (locked -- not this tool's to reschedule), else 'empty'.

    `assigned_events` and `busy_intervals` are deliberately caller-suppliable
    rather than always fetched here, so app.py can pass in a locally-cached/
    edited working set instead of forcing a live Calendar.app fetch on every
    render (a drag would otherwise re-trigger AppleScript calls on every
    rerun -- see app.py's "Plan your week" section for the session-state
    caching that fixes this). `assigned_events=None` (the default) falls
    back to a live fetch for that day, useful for standalone/one-off use.
    `busy_intervals=None` means "conflict-checking not requested for this
    day" -- every row is just 'assigned' or 'empty'; calendar_bridge.list_busy_events()
    is documented as slow (~30s per day across a handful of external
    calendars, since AppleScript's `whose` filter scans each calendar's full
    event history linearly), so it's never fetched automatically here."""
    rows = generate_day_rows(day)
    if not rows:
        return []

    if assigned_events is None:
        day_start = datetime.combine(day, time.min)
        assigned_events = calendar_bridge.list_events(day_start)
    busy_intervals = busy_intervals or []

    states: List[RowState] = []
    for row in rows:
        assigned = next(
            (ev for ev in assigned_events if _overlaps(row.start, row.work_end, ev.start, ev.end)), None
        )
        if assigned:
            states.append(RowState(row=row, status="assigned", event=assigned))
            continue

        busy = next(
            (b for b in busy_intervals if _overlaps(row.start, row.work_end, b.start, b.end)), None
        )
        if busy:
            states.append(RowState(row=row, status="busy", busy_summary=f"{busy.calendar}: {busy.summary}"))
            continue

        states.append(RowState(row=row, status="empty"))

    return states


def parse_notion_id(notes: str) -> Optional[str]:
    """Same `notion_id:<page_id>` tag format sync.py's _build_notes/_parse_notes
    use -- duplicated here as a tiny standalone parser (rather than reaching
    into sync.py's private helper) since this module deliberately doesn't
    depend on sync.py/scheduler.py."""
    for line in notes.splitlines():
        if line.startswith("notion_id:"):
            return line[len("notion_id:"):].strip()
    return None


def count_assigned_instances(events: List[calendar_bridge.CalendarEvent]) -> Dict[str, int]:
    """How many blocks (anywhere, any day) each Notion task currently
    occupies -- used to compute how many more "instance" boxes of a task
    should show up in the pool (see app.py's Plan-your-week section)."""
    counts: Dict[str, int] = defaultdict(int)
    for ev in events:
        page_id = parse_notion_id(ev.notes)
        if page_id:
            counts[page_id] += 1
    return dict(counts)
