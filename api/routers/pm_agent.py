"""
AI PM-agent (Scrum-lite feature set) -- thin wrapper around
procrastination_tool.pm_agent, matching this project's existing precedent
(character.py) of surfacing a domain error as an HTTP 400.

POST /api/pm-agent/review -- calls the configured client (real or
                              FakePMAgentClient under PM_AGENT_MOCK=1),
                              persists, and returns the suggestions. Never
                              writes to `tasks` -- see pm_agent.py's
                              module docstring for why.
GET  /api/pm-agent/last   -- the most recently persisted review, or 404
                              if none has ever been generated.
"""
from fastapi import APIRouter, HTTPException

from procrastination_tool import pm_agent

from ..schemas import PMReviewOut, PMSuggestedActionOut, PMSuggestionOut

router = APIRouter(prefix="/pm-agent", tags=["pm-agent"])


def _build_suggestion_out(s: "pm_agent.PMSuggestion") -> PMSuggestionOut:
    return PMSuggestionOut(
        id=s.id, kind=s.kind, task_id=s.task_id, title=s.title, rationale=s.rationale,
        suggested_action=(
            PMSuggestedActionOut(**vars(s.suggested_action)) if s.suggested_action else None
        ),
    )


def _build_review_out(r: "pm_agent.PMReview") -> PMReviewOut:
    return PMReviewOut(
        generated_at=r.generated_at, model_used=r.model_used,
        suggestions=[_build_suggestion_out(s) for s in r.suggestions],
    )


@router.post("/review", response_model=PMReviewOut)
def review() -> PMReviewOut:
    # get_client() is called here, not via FastAPI's Depends(), specifically
    # so PMAgentNotConfiguredError -- raised while resolving the client, not
    # while running the review -- is still catchable in this same try block.
    # Depends() would run get_client() before this function body starts,
    # which would surface the error as an unhandled 500 instead of the 400
    # this router intends.
    try:
        client = pm_agent.get_client()
        pm_agent.review_backlog(client)
    except pm_agent.PMAgentNotConfiguredError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Re-read the just-persisted row rather than hand-assembling the
    # response, so generated_at/model_used reflect exactly what was stored
    # (no second datetime.now() call, no duplicated model_used logic).
    result = pm_agent.get_last_review()
    assert result is not None  # we just persisted it
    return _build_review_out(result)


@router.get("/last", response_model=PMReviewOut)
def last_review() -> PMReviewOut:
    result = pm_agent.get_last_review()
    if result is None:
        raise HTTPException(status_code=404, detail="No PM-agent review has been generated yet")
    return _build_review_out(result)
