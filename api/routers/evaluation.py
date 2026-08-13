"""
End-of-day evaluation + mood tracker (3/3.1/3.2 in the redesign plan) --
thin wrappers around procrastination_tool.evaluation, matching this
project's existing precedent (character.py) of surfacing a domain
ValueError as an HTTP 400.

POST /api/evaluation/generate -- compute + persist (UPSERT) the snapshot
for a day (defaults to today).
GET  /api/evaluation/{date}   -- fetch a previously generated snapshot
                                  (404 if nothing's been generated for it).
GET  /api/evaluation/history  -- the last `days` generated snapshots, for
                                  a short trend view.
GET  /api/evaluation/today-status -- has today been logged yet? The
                                  end-of-day reminder banner's only data
                                  source. Registered ABOVE
                                  GET /evaluation/{eval_date} -- otherwise
                                  FastAPI tries to parse "today-status" as
                                  a date and 422s.
POST /api/mood                -- log a mood entry.
GET  /api/mood                -- that day's mood entries (today if no
                                  `date` query param).
"""
from datetime import date as date_cls
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from procrastination_tool import evaluation

from ..schemas import (
    DailyEvaluationOut,
    EvaluationGenerateRequest,
    EvaluationTodayStatusOut,
    MoodCreateRequest,
    MoodEntryOut,
)

router = APIRouter(tags=["evaluation"])


def _build_evaluation_out(e: "evaluation.DailyEvaluation") -> DailyEvaluationOut:
    return DailyEvaluationOut(
        date=e.date, generated_at=e.generated_at, sessions_count=e.sessions_count,
        focused_minutes=e.focused_minutes, completion_rate=e.completion_rate,
        tasks_completed_count=e.tasks_completed_count, runes_earned=e.runes_earned,
        mood_avg=e.mood_avg,
        mood_entries=[MoodEntryOut(**vars(m)) for m in e.mood_entries],
        tasks_completed_names=e.tasks_completed_names,
        quadrant_breakdown=e.quadrant_breakdown,
    )


@router.post("/evaluation/generate", response_model=DailyEvaluationOut)
def generate_evaluation(body: EvaluationGenerateRequest) -> DailyEvaluationOut:
    result = evaluation.generate_daily_evaluation(body.date)
    return _build_evaluation_out(result)


@router.get("/evaluation/history", response_model=List[DailyEvaluationOut])
def get_evaluation_history(days: int = Query(7, ge=1, le=90)) -> List[DailyEvaluationOut]:
    return [_build_evaluation_out(e) for e in evaluation.list_evaluations(days)]


@router.get("/evaluation/today-status", response_model=EvaluationTodayStatusOut)
def get_today_status() -> EvaluationTodayStatusOut:
    today = date_cls.today()
    return EvaluationTodayStatusOut(
        date=today,
        mood_logged=bool(evaluation.list_mood_entries(today)),
        evaluation_generated=evaluation.get_evaluation(today) is not None,
    )


@router.get("/evaluation/{eval_date}", response_model=DailyEvaluationOut)
def get_evaluation(eval_date: date_cls) -> DailyEvaluationOut:
    result = evaluation.get_evaluation(eval_date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No evaluation generated for {eval_date}")
    return _build_evaluation_out(result)


@router.post("/mood", response_model=MoodEntryOut)
def create_mood_entry(body: MoodCreateRequest) -> MoodEntryOut:
    try:
        entry = evaluation.log_mood(body.mood_score, body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return MoodEntryOut(**vars(entry))


@router.get("/mood", response_model=List[MoodEntryOut])
def list_mood_entries(mood_date: Optional[date_cls] = Query(None, alias="date")) -> List[MoodEntryOut]:
    entries = evaluation.list_mood_entries(mood_date or date_cls.today())
    return [MoodEntryOut(**vars(m)) for m in entries]
