"""
GET /api/sessions/recent?limit=50 -- wraps focus_timer.get_recent_sessions()
GET /api/sessions/stats?days=7 -- mirrors app.py's "Focus sessions" stat block,
generalized from app.py's hardcoded 7 days to the `days` query param.
"""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query

from procrastination_tool import auth, focus_timer

from ..deps import get_current_user
from ..schemas import SessionOut, StatsOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/recent", response_model=List[SessionOut])
def get_recent_sessions(
    limit: int = Query(50, ge=1), user: auth.User = Depends(get_current_user)
) -> List[SessionOut]:
    sessions = focus_timer.get_recent_sessions(user.id, limit=limit)
    return [SessionOut(**vars(s)) for s in sessions]


@router.get("/stats", response_model=StatsOut)
def get_stats(
    days: int = Query(7, ge=1), user: auth.User = Depends(get_current_user)
) -> StatsOut:
    # get_recent_sessions is ordered id DESC with a fixed limit -- app.py
    # uses limit=50 for the same "recent sessions" fetch this stat block
    # windows down from, so mirror that here too.
    sessions = focus_timer.get_recent_sessions(user.id, limit=50)

    window_start = datetime.now() - timedelta(days=days)
    window_sessions = [s for s in sessions if s.start_time >= window_start]
    completed_window = [s for s in window_sessions if s.completed]

    completion_rate = (
        len(completed_window) / len(window_sessions) if window_sessions else None
    )
    focused_minutes = sum(s.actual_minutes for s in completed_window)

    daily_minutes: dict = {}
    for i in range(days - 1, -1, -1):
        day = (datetime.now() - timedelta(days=i)).date()
        daily_minutes[day.strftime("%a %d")] = 0.0
    for s in completed_window:
        key = s.start_time.date().strftime("%a %d")
        if key in daily_minutes:
            daily_minutes[key] += s.actual_minutes

    return StatsOut(
        sessions=len(window_sessions),
        completion_rate=completion_rate,
        focused_minutes=focused_minutes,
        daily_minutes=daily_minutes,
    )
