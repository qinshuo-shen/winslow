"""
GET /api/tasks -- wraps notion_tasks.fetch_actionable_tasks() via
notion_cache (not called directly -- see notion_cache.py's docstring: this
endpoint, plus planner.py's _find_task() on the drag hot path, calling it
live and uncached on every request was the same anti-pattern that already
caused a real production AppleScript timeout on the calendar side).
Extended (Phase 4) with each task's assigned_count (how many Focus-Blocks-
calendar events, any day, are already tagged with its page_id) via
block_grid.count_assigned_instances(calendar_cache.get_all_events()) --
this is what the frontend's task pool uses to compute how many more
instances of a task are available to drag. Reads through calendar_cache
(not calendar_bridge directly) -- see calendar_cache.py's docstring for why:
this endpoint calling calendar_bridge.list_all_events() live on every
request was the direct cause of a real production AppleScript timeout.

POST /api/tasks/{page_id}/complete -- wraps the new
sync.complete_task_and_cleanup(page_id) shared helper: marks the task
Completed in Notion (a real write) and deletes every calendar block tagged
with it. Mirrors app.py's "✓ Done" button. Invalidates both calendar_cache
(deletes calendar events) and notion_cache (changes the task's Completed
status in Notion, so it should no longer appear in the next fetch).

Errors from calendar_bridge/notion_tasks are surfaced as a 500 with the
real error message, matching calendar.py's precedent, rather than falling
through to FastAPI's generic detail-less 500.
"""
from typing import List

from fastapi import APIRouter, HTTPException

from procrastination_tool import block_grid, sync

from .. import calendar_cache, notion_cache
from ..schemas import CompleteTaskOut, TaskOut

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=List[TaskOut])
def get_tasks() -> List[TaskOut]:
    try:
        tasks = notion_cache.get_tasks()
        assigned_counts = block_grid.count_assigned_instances(calendar_cache.get_all_events())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Couldn't load tasks: {e}")
    return [
        TaskOut(**t._asdict(), assigned_count=assigned_counts.get(t.page_id, 0))
        for t in tasks
    ]


@router.post("/tasks/{page_id}/complete", response_model=CompleteTaskOut)
def complete_task(page_id: str) -> CompleteTaskOut:
    try:
        removed = sync.complete_task_and_cleanup(page_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Couldn't complete task: {e}")
    notion_cache.invalidate()
    if removed:
        calendar_cache.invalidate()
    return CompleteTaskOut(removed_blocks=removed)
