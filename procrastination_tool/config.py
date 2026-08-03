import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or None
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID") or None
FOCUS_CALENDAR_NAME = os.environ.get("FOCUS_CALENDAR_NAME", "Focus Blocks")

# Calendars (beyond FOCUS_CALENDAR_NAME, always included) that count as
# "busy" time when computing free slots -- confirmed with the user
# 2026-08-02, not guessed: their Outlook work calendar syncs into
# Calendar.app as "iCloud-work", plus "PQi" and "个人" (Personal).
BUSY_CALENDARS = [
    c.strip() for c in os.environ.get(
        "BUSY_CALENDARS", "iCloud-work,PQi,个人"
    ).split(",") if c.strip()
]

# Working-hours schedule. Monday-Friday: 9:00-18:00 with a 12:00-13:00
# lunch break excluded (confirmed with the user 2026-08-02). Saturday is
# fully excluded. Python date.weekday(): Mon=0 ... Sun=6.
WORKING_WEEKDAYS = {0, 1, 2, 3, 4, 6}
WORK_START_HOUR = 9
WORK_END_HOUR = 18
LUNCH_START_HOUR = 12
LUNCH_END_HOUR = 13

# Sunday gets its own, separate window (confirmed 2026-08-02, revised same
# day from the original 9-18 assumption): 15:00-21:00, no lunch split (the
# window doesn't overlap 12-13 anyway). Only "light" tasks (Quick Wins +
# Fill-ins -- see notion_tasks.LIGHT_PRIORITIES) are ever scheduled into
# it -- Major Projects/Thankless Tasks never land on Sunday, even if
# overdue; they roll to the next available weekday instead. See
# scheduler.py's day-eligibility check in schedule_tasks().
SUNDAY_START_HOUR = 15
SUNDAY_END_HOUR = 21

DEFAULT_TASK_DURATION_MINUTES = int(os.environ.get("DEFAULT_TASK_DURATION_MINUTES", "60"))
SCHEDULING_HORIZON_DAYS = int(os.environ.get("SCHEDULING_HORIZON_DAYS", "10"))

# Phase 2: focus timer + spin wheel.
FOCUS_SESSION_MINUTES = float(os.environ.get("FOCUS_SESSION_MINUTES", "25"))

# Pause/resume follow-up: if the CURRENT pause (not cumulative pause time
# across a session's multiple pause/resume cycles -- confirmed with the
# user) lasts longer than this, the session auto-fails -- no reward,
# distinct from both a full completion and a manual Ctrl-C stop.
PAUSE_FAIL_MINUTES = float(os.environ.get("PAUSE_FAIL_MINUTES", "20"))
SPIN_WHEEL_CONFIG_PATH = PROJECT_ROOT / "spin_wheel_config.json"

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
SESSION_DB_PATH = DATA_DIR / "sessions.db"
