"""
GET /api/planner/week-range -- {today, week_end, days}
GET /api/planner/grid/{day}?check_conflicts=false -- wraps block_grid.get_row_states

`check_conflicts` MUST default to false: turning it on triggers
calendar_bridge.list_busy_events(), a documented ~30s-per-day AppleScript
call across the user's external ("busy") calendars. Never call it
unconditionally.

Phase 4 adds the real, immediate-write drag-and-drop endpoints (the
Streamlit version batched these behind a Submit button purely as a
Streamlit-rerun-cost workaround -- the React version writes to Calendar.app
on every drag, per the user's explicit decision):

POST   /api/planner/assign      -- drag a pool task onto an empty row
DELETE /api/planner/assign/{uid} -- drag an assigned box back to the pool
POST   /api/planner/move        -- drag an assigned box to a different row
POST   /api/planner/refresh     -- sync._reconcile_calendar_with_notion()

assign/move both server-side validate row_start/row_end against
block_grid.generate_day_rows(day) before writing anything -- defense
against a stale/tampered client, never trust client-supplied row times.

All Focus-Blocks-calendar reads go through calendar_cache (not
calendar_bridge directly) -- see calendar_cache.py's docstring: an uncached
live AppleScript call per request across these endpoints was the direct
cause of a real production timeout. Every write (assign/unassign/move/
refresh) calls calendar_cache.invalidate() so the next read reflects it
immediately. Task lookups (_find_task) go through notion_cache for the same
reason -- see notion_cache.py's docstring.

Errors from calendar_bridge/notion_tasks are surfaced as a 500 with the real
error message, matching calendar.py's precedent, rather than falling
through to FastAPI's generic detail-less 500 -- so a live AppleScript/Notion
failure during a drag is at least legible instead of a silent opaque error.
"""
from datetime import date as date_cls
from datetime import datetime, time, timedelta
from typing import List

from fastapi import APIRouter, HTTPException, Query

from procrastination_tool import block_grid, calendar_bridge, notion_tasks, sync
from procrastination_tool.config import BUSY_CALENDARS

from .. import calendar_cache, notion_cache
from ..schemas import (
    AssignedEventOut,
    AssignRequest,
    DeleteAssignOut,
    GridOut,
    MoveRequest,
    PlannerRefreshOut,
    RowStateOut,
    WeekRangeOut,
)

router = APIRouter(prefix="/planner", tags=["planner"])


def _validate_row(day: date_cls, row_start: datetime, row_end: datetime) -> None:
    """Reject (400) unless (row_start, row_end) exactly matches one of
    block_grid.generate_day_rows(day)'s rows -- row_end corresponds to a
    row's work_end (the 45-min work portion the calendar event actually
    covers), not its break_end."""
    rows = block_grid.generate_day_rows(day)
    if not any(r.start == row_start and r.work_end == row_end for r in rows):
        raise HTTPException(
            status_code=400,
            detail=f"{row_start}–{row_end} is not a valid block row for {day}",
        )


def _find_task(page_id: str) -> notion_tasks.Task:
    for t in notion_cache.get_tasks():
        if t.page_id == page_id:
            return t
    raise HTTPException(status_code=404, detail=f"No actionable task with page_id {page_id!r}")


@router.get("/week-range", response_model=WeekRangeOut)
def get_week_range() -> WeekRangeOut:
    today = date_cls.today()
    week_end = notion_tasks.get_week_end(today)
    days = [today + timedelta(days=i) for i in range((week_end - today).days + 1)]
    return WeekRangeOut(today=today, week_end=week_end, days=days)


@router.get("/grid/{day}", response_model=GridOut)
def get_grid(day: date_cls, check_conflicts: bool = Query(False)) -> GridOut:
    try:
        busy_intervals = None
        if check_conflicts:
            busy_intervals = calendar_bridge.list_busy_events(
                datetime.combine(day, time.min), BUSY_CALENDARS
            )

        row_states = block_grid.get_row_states(
            day, assigned_events=calendar_cache.get_events_for_day(day), busy_intervals=busy_intervals
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Couldn't load the day's grid: {e}")

    rows: List[RowStateOut] = []
    for rs in row_states:
        rows.append(RowStateOut(
            row={
                "start": rs.row.start,
                "work_end": rs.row.work_end,
                "break_end": rs.row.break_end,
            },
            status=rs.status,
            event=rs.event._asdict() if rs.event is not None else None,
            busy_summary=rs.busy_summary,
        ))

    return GridOut(day=day, check_conflicts=check_conflicts, rows=rows)


@router.post("/assign", response_model=AssignedEventOut)
def assign_task(body: AssignRequest) -> AssignedEventOut:
    _validate_row(body.day, body.row_start, body.row_end)
    task = _find_task(body.page_id)
    notes = sync._build_notes(task)
    try:
        uid = calendar_bridge.create_event(task.name, body.row_start, body.row_end, notes=notes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Couldn't create the calendar block: {e}")
    calendar_cache.invalidate()
    return AssignedEventOut(uid=uid, summary=task.name, start=body.row_start, end=body.row_end, notes=notes)


@router.delete("/assign/{uid}", response_model=DeleteAssignOut)
def unassign_task(uid: str) -> DeleteAssignOut:
    try:
        deleted = calendar_bridge.delete_event_by_uid(uid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Couldn't delete the calendar block: {e}")
    if deleted:
        calendar_cache.invalidate()
    return DeleteAssignOut(deleted=deleted)


@router.post("/move", response_model=AssignedEventOut)
def move_task(body: MoveRequest) -> AssignedEventOut:
    _validate_row(body.day, body.row_start, body.row_end)

    existing = next((ev for ev in calendar_cache.get_all_events() if ev.uid == body.uid), None)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No calendar event with uid {body.uid!r}")

    page_id = block_grid.parse_notion_id(existing.notes)
    if not page_id:
        raise HTTPException(status_code=400, detail="Event has no notion_id tag; can't resolve its task")

    # Fresh task lookup, not the stale data baked into the old event's notes
    # -- priority/name may have changed in Notion since the original assign.
    task = _find_task(page_id)
    notes = sync._build_notes(task)

    # Delete-then-create, in that order, inside this one request -- atomic
    # from the client's perspective even though it's two Calendar.app writes.
    # If create fails after delete succeeds, the old block is already gone --
    # invalidate unconditionally (in `finally`, not just on the success path)
    # so the cache can never keep serving a stale "still there" view for the
    # rest of its TTL, and surface the failure loudly rather than silently
    # losing the block behind that stale window.
    deleted_old = False
    try:
        calendar_bridge.delete_event_by_uid(body.uid)
        deleted_old = True
        new_uid = calendar_bridge.create_event(task.name, body.row_start, body.row_end, notes=notes)
    except Exception as e:
        if deleted_old:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Moved event was deleted but recreation failed: {e}. "
                    f"Check Calendar.app and re-add '{task.name}' manually."
                ),
            )
        raise HTTPException(status_code=500, detail=f"Couldn't move the calendar block: {e}")
    finally:
        calendar_cache.invalidate()
    return AssignedEventOut(uid=new_uid, summary=task.name, start=body.row_start, end=body.row_end, notes=notes)


@router.post("/refresh", response_model=PlannerRefreshOut)
def refresh_planner() -> PlannerRefreshOut:
    log: List[str] = []
    try:
        removed_count = sync._reconcile_calendar_with_notion(log.append)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Couldn't refresh: {e}")
    if removed_count:
        calendar_cache.invalidate()
    return PlannerRefreshOut(removed_count=removed_count, log=log)
