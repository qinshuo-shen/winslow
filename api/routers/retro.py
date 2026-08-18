"""
Weekly retro (Scrum-lite feature set) -- thin wrappers around
procrastination_tool.evaluation's weekly_retros functions, mirroring
routers/evaluation.py's daily-evaluation endpoints exactly (same
generate/history/{key} triad, same UPSERT-on-generate semantics).

POST /api/retro/generate      -- compute + persist (UPSERT) the retro for
                                  a week (defaults to the current week; any
                                  date within the week is accepted).
GET  /api/retro/history        -- the last `weeks` generated retros, for
                                  the velocity trend view.
GET  /api/retro/{week_start}   -- fetch a previously generated retro (404
                                  if nothing's been generated for it).
"""
from datetime import date as date_cls
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from procrastination_tool import auth, evaluation

from ..deps import get_current_user
from ..schemas import WeeklyRetroGenerateRequest, WeeklyRetroOut

router = APIRouter(prefix="/retro", tags=["retro"])


def _build_retro_out(r: "evaluation.WeeklyRetro") -> WeeklyRetroOut:
    return WeeklyRetroOut(
        week_start=r.week_start, week_end=r.week_end, generated_at=r.generated_at,
        sessions_count=r.sessions_count, focused_minutes=r.focused_minutes,
        tasks_completed_count=r.tasks_completed_count, committed_count=r.committed_count,
        committed_completed_count=r.committed_completed_count, mood_avg=r.mood_avg,
        tasks_completed_names=r.tasks_completed_names,
        quadrant_breakdown=r.quadrant_breakdown,
    )


@router.post("/generate", response_model=WeeklyRetroOut)
def generate_retro(
    body: WeeklyRetroGenerateRequest, user: auth.User = Depends(get_current_user)
) -> WeeklyRetroOut:
    result = evaluation.generate_weekly_retro(user.id, body.week_start)
    return _build_retro_out(result)


@router.get("/history", response_model=List[WeeklyRetroOut])
def get_retro_history(
    weeks: int = Query(6, ge=1, le=12), user: auth.User = Depends(get_current_user)
) -> List[WeeklyRetroOut]:
    return [_build_retro_out(r) for r in evaluation.list_weekly_retros(user.id, weeks)]


@router.get("/{week_start}", response_model=WeeklyRetroOut)
def get_retro(
    week_start: date_cls, user: auth.User = Depends(get_current_user)
) -> WeeklyRetroOut:
    result = evaluation.get_weekly_retro(user.id, week_start)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No retro generated for week of {week_start}")
    return _build_retro_out(result)
