"""
Project tracking (2026-08 page-split redesign) -- CRUD over
procrastination_tool.projects, plus a task-breakdown read endpoint backing
the frontend's roadmap timeline. Same shape as routers/backlog.py
(HTTPException(400) on a domain ValueError, 404 on a missing id).
"""
from typing import List

from fastapi import APIRouter, HTTPException

from procrastination_tool import projects, tasks

from ..schemas import BacklogTaskOut, ProjectCreateRequest, ProjectOut, ProjectUpdateRequest
from .backlog import _build_task_out

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=List[ProjectOut])
def list_projects() -> List[ProjectOut]:
    return [ProjectOut(**vars(p)) for p in projects.list_projects()]


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreateRequest) -> ProjectOut:
    try:
        project = projects.add_project(name=body.name, notes=body.notes, tags=body.tags)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ProjectOut(**vars(project))


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int) -> ProjectOut:
    project = projects.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectOut(**vars(project))


@router.patch("/{project_id}", response_model=ProjectOut)
def patch_project(project_id: int, body: ProjectUpdateRequest) -> ProjectOut:
    if projects.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        project = projects.update_project(
            project_id, name=body.name, status=body.status, notes=body.notes, tags=body.tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ProjectOut(**vars(project))


@router.delete("/{project_id}")
def delete_project(project_id: int) -> dict:
    if projects.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    projects.delete_project(project_id)
    return {"deleted": True}


@router.get("/{project_id}/tasks", response_model=List[BacklogTaskOut])
def list_project_tasks(project_id: int) -> List[BacklogTaskOut]:
    """Backs the Project roadmap's vertical milestone timeline."""
    if projects.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [_build_task_out(t) for t in tasks.list_tasks_for_project(project_id)]
