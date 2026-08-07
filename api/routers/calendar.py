"""
GET /api/calendar/today -- mirrors app.py's "Today's schedule" section
(today's Focus-Blocks-calendar events, sorted). Reads through
calendar_cache.get_events_for_day() rather than calling
calendar_bridge.list_events() directly on every request -- see
calendar_cache.py's docstring for why (an uncached live AppleScript call
here was part of what caused a real production timeout).

app.py wraps its equivalent call in try/except and surfaces calendar-read
failures (AppleScript/Calendar.app errors) via st.error with the exact
message "Couldn't read the {FOCUS_CALENDAR_NAME} calendar: {e}", falling
back to an empty list only for the *no-events* case. Preserved here as a
500 with that same detail string, rather than swallowing failures into an
empty list -- that would collapse "calendar read failed" and "no events
today" into the same frontend empty-state, which app.py deliberately does
not do.
"""
from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException

from procrastination_tool.config import FOCUS_CALENDAR_NAME

from .. import calendar_cache
from ..schemas import CalendarEventOut

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/today", response_model=List[CalendarEventOut])
def get_today_events() -> List[CalendarEventOut]:
    try:
        events = sorted(calendar_cache.get_events_for_day(date.today()), key=lambda e: e.start)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't read the {FOCUS_CALENDAR_NAME} calendar: {e}",
        )
    return [CalendarEventOut(**e._asdict()) for e in events]
