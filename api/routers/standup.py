"""
Virtual daily standup (Scrum-lite feature set) -- thin wrapper around
procrastination_tool.standup, matching pm_agent.py's precedent of
surfacing a domain "not configured" error as an HTTP 400.

POST /api/standup/generate -- calls the configured client (real or
                               FakeStandupClient under STANDUP_MOCK=1),
                               persists the note, returns it.
GET  /api/standup/today    -- today's already-generated note, or 404 if
                               none has been generated yet today.
"""
from fastapi import APIRouter, HTTPException

from procrastination_tool import standup

from ..schemas import StandupGenerateRequest, StandupOut

router = APIRouter(prefix="/standup", tags=["standup"])


def _build_standup_out(n: "standup.StandupNote") -> StandupOut:
    return StandupOut(
        generated_at=n.generated_at, model_used=n.model_used,
        note_date=n.note_date, note=n.note,
    )


@router.post("/generate", response_model=StandupOut)
def generate(body: StandupGenerateRequest) -> StandupOut:
    # get_client() is called here, not via Depends(), for the same reason
    # pm_agent.py's router does this -- see that module's comment.
    try:
        client = standup.get_client()
        result = standup.generate_standup(client, question=body.question)
    except standup.StandupNotConfiguredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _build_standup_out(result)


@router.get("/today", response_model=StandupOut)
def today() -> StandupOut:
    result = standup.get_today_note()
    if result is None:
        raise HTTPException(status_code=404, detail="No standup has been generated yet today")
    return _build_standup_out(result)
