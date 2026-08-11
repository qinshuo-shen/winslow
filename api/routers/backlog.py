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
from typing import List

from fastapi import APIRouter, HTTPException

from procrastination_tool import tasks

from ..schemas import BacklogTaskCreateRequest, BacklogTaskOut, BacklogTaskUpdateRequest

router = APIRouter(prefix="/backlog", tags=["backlog"])


@router.get("", response_model=List[BacklogTaskOut])
def list_backlog() -> List[BacklogTaskOut]:
    return [BacklogTaskOut(**vars(t)) for t in tasks.list_all_tasks()]


@router.post("", response_model=BacklogTaskOut)
def create_task(body: BacklogTaskCreateRequest) -> BacklogTaskOut:
    try:
        task = tasks.add_task(
            name=body.name, priority=body.priority, notes=body.notes,
            specific_project=body.specific_project, tags=body.tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BacklogTaskOut(**vars(task))


@router.patch("/{task_id}", response_model=BacklogTaskOut)
def patch_task(task_id: int, body: BacklogTaskUpdateRequest) -> BacklogTaskOut:
    if tasks.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        task = tasks.update_task(
            task_id,
            name=body.name, priority=body.priority, notes=body.notes,
            status=body.status, specific_project=body.specific_project,
            is_today=body.is_today, position=body.position, tags=body.tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BacklogTaskOut(**vars(task))


@router.post("/{task_id}/complete", response_model=BacklogTaskOut)
def complete_task(task_id: int) -> BacklogTaskOut:
    task = tasks.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks.mark_completed(task_id)
    task = tasks.get_task(task_id)
    return BacklogTaskOut(**vars(task))


@router.delete("/{task_id}")
def delete_task(task_id: int) -> dict:
    if tasks.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks.delete_task(task_id)
    return {"deleted": True}
