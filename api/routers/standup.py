"""
Virtual daily standup (Scrum-lite feature set) -- thin wrapper around
procrastination_tool.standup, surfacing a domain "not configured" error as
an HTTP 400 (a convention inherited from the retired PM-agent router).

POST /api/standup/generate -- calls the configured client (real or
                               FakeStandupClient under STANDUP_MOCK=1),
                               persists the note, returns it.
GET  /api/standup/today    -- today's already-generated note, or 404 if
                               none has been generated yet today.
"""
from fastapi import APIRouter, Depends, HTTPException

from procrastination_tool import auth, standup

from ..deps import get_current_user
from ..schemas import StandupGenerateRequest, StandupOut

router = APIRouter(prefix="/standup", tags=["standup"])


def _build_standup_out(n: "standup.StandupNote") -> StandupOut:
    return StandupOut(
        generated_at=n.generated_at, model_used=n.model_used,
        note_date=n.note_date, note=n.note,
    )


@router.post("/generate", response_model=StandupOut)
def generate(
    body: StandupGenerateRequest, user: auth.User = Depends(get_current_user)
) -> StandupOut:
    # get_client() is called here, not via FastAPI's Depends(), specifically
    # so StandupNotConfiguredError -- raised while resolving the client, not
    # while generating the note -- is still catchable in this same try block.
    # Depends() would run get_client() before this function body starts,
    # which would surface the error as an unhandled 500 instead of the 400
    # this router intends. (Reasoning inlined 2026-09-06 from the retired
    # PM-agent router, which is where this comment used to point.)
    try:
        client = standup.get_client()
        result = standup.generate_standup(user.id, client, question=body.question)
    except standup.StandupNotConfiguredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _build_standup_out(result)


@router.get("/today", response_model=StandupOut)
def today(user: auth.User = Depends(get_current_user)) -> StandupOut:
    result = standup.get_today_note(user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="No standup has been generated yet today")
    return _build_standup_out(result)
