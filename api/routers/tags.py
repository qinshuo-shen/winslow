"""
GET  /api/tags -- every tag ever created (procrastination_tool.tasks.
list_tags()), alphabetical, each with its `parent` (None for a top-level
"Project" tag) -- the source for the Board's project filter tabs and the
tag editor's project/sub-tag picker.
POST /api/tags -- create a tag, or set/replace an existing tag's parent.
Used by the tag editor when the user types a brand-new sub-tag under a
chosen project (created immediately, before the task itself is saved, so
its parent is recorded correctly).

A separate router (not nested under /backlog) since a tag isn't scoped to
one task -- see tasks.py's module docstring for the tags/task_tags/
parent_id design.
"""
from typing import List

from fastapi import APIRouter, HTTPException

from procrastination_tool import tasks

from ..schemas import TagCreateRequest, TagOut

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=List[TagOut])
def list_tags() -> List[TagOut]:
    return [TagOut(name=t.name, parent=t.parent) for t in tasks.list_tags()]


@router.post("", response_model=TagOut)
def create_tag(body: TagCreateRequest) -> TagOut:
    try:
        info = tasks.set_tag_parent(body.name, body.parent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TagOut(name=info.name, parent=info.parent)
