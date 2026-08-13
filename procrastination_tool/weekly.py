"""
Shared week-boundary utility for the sprint/retro/velocity feature set.

Monday-start, matching the only prior "week" precedent in this codebase
(deadlines._week_start(), which computes the same thing for the dormant
weekly-pass-limit feature) -- promoted here as a public, date-based (not
datetime-based) helper so tasks.py/evaluation.py/pm_agent.py all compute
"which week" the same way instead of each rolling their own.
"""
from datetime import date, timedelta
from typing import Tuple


def week_start_date(d: date) -> date:
    """The Monday of the week containing `d`."""
    return d - timedelta(days=d.weekday())


def week_bounds(d: date) -> Tuple[date, date]:
    """(Monday, Sunday) of the week containing `d`, both inclusive."""
    start = week_start_date(d)
    return start, start + timedelta(days=6)
