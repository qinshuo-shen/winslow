import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or None
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID") or None
FOCUS_CALENDAR_NAME = os.environ.get("FOCUS_CALENDAR_NAME", "Focus Blocks")

# "Hardcore" focus sessions (optional calendar block, confirmed with the
# user): must be the EXACT name of the user's own already-Exchange-synced
# calendar as it already appears in Calendar.app -- NOT a calendar this
# tool creates (unlike FOCUS_CALENDAR_NAME). calendar_bridge.create_event's
# ensure_calendar() call is a harmless no-op here since the calendar
# already exists; if this is left unset/wrong, hardcore session starts will
# fail loudly (AppleScript error) rather than silently writing to the wrong
# place.
EXCHANGE_CALENDAR_NAME = os.environ.get("EXCHANGE_CALENDAR_NAME") or None

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
# lunch break excluded (confirmed with the user 2026-08-02). Python
# date.weekday(): Mon=0 ... Sun=6. Saturday(5) was originally excluded
# entirely; added 2026-08-06 when the manual drag-and-drop block grid
# (block_grid.py) replaced the old automatic scheduler -- Saturday now
# shares Sunday's window (see WEEKEND_START_HOUR/END_HOUR below).
WORKING_WEEKDAYS = {0, 1, 2, 3, 4, 5, 6}
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
# scheduler.py's day-eligibility check in schedule_tasks(). scheduler.py
# is disconnected from the live app now (see block_grid.py), and its only
# remaining trigger -- the daily/on-login LaunchAgent calling
# scripts/sync_tasks.py -- was itself unloaded 2026-08-07 after it was found
# still auto-creating calendar blocks in competition with the manual grid
# (see scripts/sync_tasks.py's docstring). scheduler.py stays on disk and
# still imports these names, so they're kept as-is rather than renamed.
SUNDAY_START_HOUR = 15
SUNDAY_END_HOUR = 21

# WEEKEND_START_HOUR/END_HOUR (2026-08-06, manual block grid): the canonical
# names block_grid.py uses for BOTH Saturday and Sunday's window -- same
# values as SUNDAY_START_HOUR/END_HOUR above, just not Sunday-specific,
# since Saturday now gets the same hours (confirmed with the user) rather
# than being excluded.
WEEKEND_START_HOUR = SUNDAY_START_HOUR
WEEKEND_END_HOUR = SUNDAY_END_HOUR
SATURDAY = 5
SUNDAY = 6

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

# RPG reward system (2026-08-06 redesign, replaces the spin wheel -- see
# procrastination_tool/character.py). Runes earned per completed session =
# actual_minutes * PRIORITY_RUNE_MULTIPLIER[priority] * BASE_RUNES_PER_MINUTE.
# The Thankless Tasks (1.8) and Major Projects (1.1) multipliers are a
# deliberate bias: Major Projects are already self-motivating on their own,
# Thankless Tasks are exactly what tends to get under-rewarded otherwise.
# Quick Wins/Fill-ins values are reasonable defaults, not independently
# tuned yet -- change them directly if they don't feel right, same as
# notion_tasks.PRIORITY_DURATION_MINUTES.
BASE_RUNES_PER_MINUTE = 3.0
PRIORITY_RUNE_MULTIPLIER = {
    "Thankless Tasks (Low Impact-High Effort)": 1.8,
    "Major Projects (High Impact-High Effort)": 1.1,
    "Quick Wins (High Impact-Low Effort)": 1.3,
    "Fill-ins (Low Impact-Low Effort)": 1.0,
}
DEFAULT_RUNE_MULTIPLIER = 1.0  # untagged/free-text sessions with no linked Notion priority

# Bonfire-style leveling: Runes only convert to a permanent stat level via
# the deliberate `focus rest` action, never automatically on earning them.
# Cost to level a given stat FROM `current_level` TO `current_level + 1`.
# Not independently tuned yet -- adjust freely.
def stat_level_cost(current_level: int) -> int:
    return 100 * (current_level + 1)

CHARACTER_STATS = ["Intelligence", "Vigor", "Dexterity", "Endurance"]

# Bloodstain recovery window (Souls-style: a failed session's Runes sit in
# a bloodstain, recoverable by the next completed session within this
# window, rather than being lost outright).
BLOODSTAIN_EXPIRY_HOURS = 24

GEAR_CATALOG_PATH = PROJECT_ROOT / "gear_catalog.json"

# Flat Rune bonus paid every Nth completed session under the same Notion
# "Specific Project" tag (a light progress counter, not full quest content).
QUESTLINE_MILESTONE_SESSIONS = 5
QUESTLINE_MILESTONE_BONUS_RUNES = 200

# Manual drag-and-drop scheduling grid (2026-08-06, block_grid.py) --
# replaces the automatic scheduler.py/sync.py path in app.py. Each row is
# BLOCK_WORK_MINUTES of task time immediately followed by an implicit
# BLOCK_BREAK_MINUTES break (never its own calendar event -- same "just
# shows as free time" precedent as scheduler.py's break_fn). 45+15=60 min
# rows divide every existing hour-aligned window (weekday morning 9-12,
# weekday afternoon 13-18, weekend 15-21) with zero leftover.
BLOCK_WORK_MINUTES = 45
BLOCK_BREAK_MINUTES = 15

# Proactive scheduler (2026-08-11 redesign): auto-picks a task during
# working hours and nudges the user instead of waiting to be opened. Grace
# window is how long the user has to tap Start/Swap before the nudged task
# auto-starts on its own -- short enough to keep urgency, long enough to
# actually notice the notification. Swaps are capped so "pick something
# else" can't turn back into open-ended browsing/choice-paralysis.
AUTO_START_GRACE_SECONDS = int(os.environ.get("AUTO_START_GRACE_SECONDS", "120"))
MAX_NUDGE_CANDIDATES = int(os.environ.get("MAX_NUDGE_CANDIDATES", "3"))
MAX_NUDGE_SWAPS = int(os.environ.get("MAX_NUDGE_SWAPS", "2"))

# Deadlines/effort tracking (2026-08-11 redesign, Phase 3). A deadline
# governs ENGAGEMENT, not completion -- see deadlines.py's module docstring.
# Horizon-by-quadrant mirrors the effort-first bias PRIORITY_ORDER already
# encodes: heavier tasks get more real time before their engagement window
# closes, lighter ones are meant to be tackled same-day.
DEADLINE_HORIZON_HOURS_BY_PRIORITY = {
    "Major Projects (High Impact-High Effort)": 72,
    "Thankless Tasks (Low Impact-High Effort)": 24,
    "Quick Wins (High Impact-Low Effort)": 8,
    "Fill-ins (Low Impact-Low Effort)": 8,
}
DEFAULT_GRACE_MINUTES = int(os.environ.get("DEFAULT_GRACE_MINUTES", "15"))
WEEKLY_PASS_LIMIT = int(os.environ.get("WEEKLY_PASS_LIMIT", "1"))

# Partial credit: a session stopped early still counts as genuine effort if
# it reached this fraction of its planned length -- decided during the
# redesign brainstorm over the stricter "must fully complete" alternative,
# so a real interruption doesn't unfairly count as disengagement.
EFFORT_CREDIT_RATIO = float(os.environ.get("EFFORT_CREDIT_RATIO", "0.75"))

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
SESSION_DB_PATH = DATA_DIR / "sessions.db"
