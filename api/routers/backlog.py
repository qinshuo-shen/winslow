"""
Native task backlog (2026-08-11 redesign) -- CRUD over procrastination_tool.
tasks, the SQLite-backed replacement for the old Notion-synced task list.
Distinct from the legacy /api/tasks (routers/tasks.py, still Notion-backed
until the one-time migration -- see migrate_notion_tasks.py) so nothing
that still reads the old shape breaks mid-migration.

This is now the Board's data source (see frontend/src/components/Board) --
`GET /api/backlog` returns every task (not just actionable ones) so the
Board can render completed/on-hold tasks too, and `PATCH /api/backlog/{id}`
is the single generic endpoint the Board uses for every mutation (status
change, quadrant move, Today/Pool toggle, reorder, notes edit).
"""
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from procrastination_tool import auth, tasks
from procrastination_tool.weekly import week_start_date

from ..deps import get_current_user
from ..schemas import (
    BacklogTaskCreateRequest,
    BacklogTaskOut,
    BacklogTaskUpdateRequest,
    BacklogTodayStatusOut,
)

router = APIRouter(prefix="/backlog", tags=["backlog"])


def _build_task_out(t: tasks.Task) -> BacklogTaskOut:
    """BacklogTaskOut plus two computed flags: `carried_forward` (true only
    when this task was the one roll_over_today() chose *today*) and
    `is_current_week_commitment` (true only when week_committed_date is
    *this* week's Monday) -- both computed here rather than stored, so a
    stale marker from a previous day/week never shows as still-active."""
    fields = {
        k: v for k, v in vars(t).items()
        if k not in ("carried_forward_date", "week_committed_date")
    }
    return BacklogTaskOut(
        **fields,
        carried_forward=(t.carried_forward_date == date.today().isoformat()),
        is_current_week_commitment=(
            t.week_committed_date == week_start_date(date.today()).isoformat()
        ),
    )


@router.get("", response_model=List[BacklogTaskOut])
def list_backlog(user: auth.User = Depends(get_current_user)) -> List[BacklogTaskOut]:
    tasks.roll_over_today(user.id)
    tasks.roll_over_week(user.id)
    return [_build_task_out(t) for t in tasks.list_all_tasks(user.id)]


@router.get("/today-status", response_model=BacklogTodayStatusOut)
def get_today_status(user: auth.User = Depends(get_current_user)) -> BacklogTodayStatusOut:
    tasks.roll_over_today(user.id)
    today = date.today()
    has_today_tasks = any(t.is_today for t in tasks.list_all_tasks(user.id))
    return BacklogTodayStatusOut(date=today, has_today_tasks=has_today_tasks)


@router.post("", response_model=BacklogTaskOut)
def create_task(
    body: BacklogTaskCreateRequest, user: auth.User = Depends(get_current_user)
) -> BacklogTaskOut:
    try:
        task = tasks.add_task(
            user_id=user.id, name=body.name, priority=body.priority, notes=body.notes,
            specific_project=body.specific_project, tags=body.tags,
            project_id=body.project_id, is_draft=body.is_draft,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _build_task_out(task)


@router.patch("/{task_id}", response_model=BacklogTaskOut)
def patch_task(
    task_id: int, body: BacklogTaskUpdateRequest, user: auth.User = Depends(get_current_user)
) -> BacklogTaskOut:
    if tasks.get_task(user.id, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        task = tasks.update_task(
            user.id, task_id,
            name=body.name, priority=body.priority, notes=body.notes,
            status=body.status, specific_project=body.specific_project,
            is_today=body.is_today, position=body.position, tags=body.tags,
            is_this_week=body.is_this_week, project_id=body.project_id,
            is_draft=body.is_draft,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _build_task_out(task)


@router.post("/{task_id}/complete", response_model=BacklogTaskOut)
def complete_task(task_id: int, user: auth.User = Depends(get_current_user)) -> BacklogTaskOut:
    task = tasks.get_task(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks.mark_completed(user.id, task_id)
    task = tasks.get_task(user.id, task_id)
    return _build_task_out(task)


@router.delete("/{task_id}")
def delete_task(task_id: int, user: auth.User = Depends(get_current_user)) -> dict:
    if tasks.get_task(user.id, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks.delete_task(user.id, task_id)
    return {"deleted": True}
