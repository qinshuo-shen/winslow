"""
In-process cache for calendar_bridge.list_all_events().

Calendar.app reads via AppleScript are slow -- confirmed directly, not
assumed: list_all_events() took ~18s for 13 events, list_events() for a
single day with 4 events took ~10s (each event needs 5 property accesses
including two ISO-date coercions, each a separate, slow Apple Event round
trip). The Streamlit dashboard (app.py) deliberately read Calendar.app only
ONCE per browser session for exactly this reason (see its "local-first"
design). That discipline didn't carry over to the FastAPI migration: several
endpoints (tasks, calendar/today, planner/grid, planner/move) each called
calendar_bridge directly, uncached, on every single request -- multiplying
an already-slow call across nearly every user interaction, and the direct
cause of a real production `subprocess.TimeoutExpired` (45s timeout) hit
during normal use.

This module is the fix: the one read path for Focus-Blocks-calendar events
in the API layer. Everything that needs them reads through here and filters
in Python, instead of issuing a fresh AppleScript call per endpoint per
request. A short TTL bounds staleness from changes made OUTSIDE this app
(e.g. deleting an event directly in Calendar.app); explicit invalidate()
after every write this app itself makes means your own actions are never
stale regardless of the TTL.
"""
import time
from datetime import date
from threading import Lock
from typing import List, Optional

from procrastination_tool import calendar_bridge

_TTL_SECONDS = 30

_lock = Lock()
_cache: Optional[List[calendar_bridge.CalendarEvent]] = None
_cached_at: float = 0.0


def get_all_events(force_refresh: bool = False) -> List[calendar_bridge.CalendarEvent]:
    global _cache, _cached_at
    with _lock:
        stale = _cache is None or (time.monotonic() - _cached_at) > _TTL_SECONDS
        if force_refresh or stale:
            _cache = calendar_bridge.list_all_events()
            _cached_at = time.monotonic()
        return _cache


def get_events_for_day(day: date) -> List[calendar_bridge.CalendarEvent]:
    """Focus-Blocks-calendar events starting on `day`, derived from the
    same cached full-calendar snapshot rather than a separate
    calendar_bridge.list_events(day) AppleScript call -- this calendar only
    ever contains this tool's own writes (see calendar_bridge.py's own
    list_all_events() docstring), so filtering the full list by date is
    exactly equivalent, just without the extra round trip."""
    return [ev for ev in get_all_events() if ev.start.date() == day]


def invalidate() -> None:
    """Call after any write to the Focus Blocks calendar (create/delete)
    so the next read reflects it immediately rather than waiting out the
    TTL."""
    global _cache
    with _lock:
        _cache = None
