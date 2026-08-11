"""
GET /api/tags -- every tag that's ever been created (procrastination_tool.
tasks.list_tags()), alphabetical. The Board's autocomplete source when
tagging a task; a separate router (not nested under /backlog) since a tag
isn't scoped to one task -- see tasks.py's module docstring for the
tags/task_tags table design.
"""
from typing import List

from fastapi import APIRouter

from procrastination_tool import tasks

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=List[str])
def list_tags() -> List[str]:
    return tasks.list_tags()
