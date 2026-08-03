"""
Greedy free-slot scheduler: places Notion tasks (already fetched and
ranked by notion_tasks.fetch_actionable_tasks) into free calendar slots
within working hours, checking busy time across every calendar the user
confirmed matters (their Outlook-synced calendar plus a couple of personal
ones -- see config.BUSY_CALENDARS), not just this tool's own Focus Blocks
calendar.

Deliberately simple for Phase 1: one greedy pass in the tasks' existing
rank order, first-fit into the earliest free slot large enough for the
task's duration. Duration comes from notion_tasks.get_task_duration_minutes
(Priority-based defaults, since there's no per-task "Estimated Duration"
property in Notion yet -- see notion_tasks.py). No task-splitting across
slots, no backtracking/optimization.
"""
from datetime import date, datetime, time, timedelta
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from . import calendar_bridge
from .config import (
    BUSY_CALENDARS, LUNCH_END_HOUR, LUNCH_START_HOUR, SCHEDULING_HORIZON_DAYS,
    SUNDAY_END_HOUR, SUNDAY_START_HOUR, WORK_END_HOUR, WORK_START_HOUR,
    WORKING_WEEKDAYS,
)
from .notion_tasks import Task, get_task_break_minutes, get_task_duration_minutes, is_light_task

Interval = Tuple[datetime, datetime]

SUNDAY = 6  # date.weekday()


class Placement(NamedTuple):
    task: Task
    start: datetime
    end: datetime


def _round_up_to_next(dt: datetime, minutes: int = 5) -> datetime:
    """Round `dt` up to the next clean N-minute mark (e.g. 10:17:42 -> 10:20)."""
    discard = timedelta(minutes=dt.minute % minutes, seconds=dt.second, microseconds=dt.microsecond)
    dt -= discard
    if discard > timedelta(0):
        dt += timedelta(minutes=minutes)
    return dt


def _work_blocks_for_day(day: date, floor: Optional[datetime] = None) -> List[Interval]:
    """
    Working-hours intervals for `day`. Empty list on non-working days.
    Sunday gets its own separate, narrower window (config.SUNDAY_START_HOUR/
    END_HOUR) with no lunch split; Monday-Friday split around the lunch
    break as usual. Which *tasks* are allowed on Sunday (light-only) is
    enforced separately in schedule_tasks(), not here -- this function only
    knows about time-of-day, not task priority.

    `floor`, if given, is the earliest instant any block for `day` may
    start -- every block's start is clipped to `max(block_start, floor)`,
    and a block whose clipped start would land at or after its own end
    (e.g. floor is already past WORK_END_HOUR, or inside/past lunch for the
    morning block) is dropped entirely rather than emitted as a zero/
    negative-length interval. schedule_tasks() passes two different kinds
    of floor through this same mechanism: today's actual wall-clock time
    (so a same-day resync can't offer up a slot already in the past --
    confirmed 2026-08-03 after a new Fill-ins task synced into a 9:00-9:30
    slot at 10:15am), and, for a light/Low-Effort task, the end of the
    latest heavy/High-Effort task placed on that same day *this run* (so a
    light task can't chronologically land earlier in the day than a heavy
    one just because it happens to fit a small leftover gap the heavy task
    didn't -- confirmed 2026-08-03 after a Fill-ins task landed at 10:35am,
    hours before a Major Projects task scheduled the same day at 1pm).
    """
    if day.weekday() not in WORKING_WEEKDAYS:
        return []
    if day.weekday() == SUNDAY:
        blocks = [(datetime.combine(day, time(SUNDAY_START_HOUR, 0)), datetime.combine(day, time(SUNDAY_END_HOUR, 0)))]
    else:
        morning = (datetime.combine(day, time(WORK_START_HOUR, 0)), datetime.combine(day, time(LUNCH_START_HOUR, 0)))
        afternoon = (datetime.combine(day, time(LUNCH_END_HOUR, 0)), datetime.combine(day, time(WORK_END_HOUR, 0)))
        blocks = [morning, afternoon]

    if floor is not None:
        blocks = [(max(start, floor), end) for start, end in blocks]
        blocks = [(start, end) for start, end in blocks if start < end]

    return blocks


def _subtract_busy(free_blocks: List[Interval], busy_intervals: List[Interval]) -> List[Interval]:
    for busy_start, busy_end in sorted(busy_intervals):
        next_blocks = []
        for f_start, f_end in free_blocks:
            if busy_end <= f_start or busy_start >= f_end:
                next_blocks.append((f_start, f_end))  # no overlap with this busy interval
                continue
            if busy_start > f_start:
                next_blocks.append((f_start, busy_start))
            if busy_end < f_end:
                next_blocks.append((busy_end, f_end))
        free_blocks = next_blocks
    return free_blocks


def compute_free_slots(day: date, busy_intervals: List[Interval], floor: Optional[datetime] = None) -> List[Interval]:
    return _subtract_busy(_work_blocks_for_day(day, floor=floor), busy_intervals)


def schedule_tasks(tasks: List[Task], start_day: Optional[date] = None,
                    horizon_days: int = SCHEDULING_HORIZON_DAYS,
                    duration_fn: Optional[Callable[[Task], int]] = None,
                    break_fn: Optional[Callable[[Task], int]] = None,
                    busy_calendars: Optional[List[str]] = None,
                    now: Optional[datetime] = None) -> Tuple[List[Placement], List[Task]]:
    """
    Greedily place each task (in the order given -- already ranked by the
    caller) into the earliest free slot across the horizon large enough
    for that task's own duration (duration_fn(task), minutes -- defaults
    to notion_tasks.get_task_duration_minutes, i.e. Priority-based).
    Returns (placements, unscheduled_tasks). Busy time is queried once per
    day actually reached (lazily cached), not once per task, to keep the
    number of AppleScript round-trips small.

    After each placement, a break (break_fn(task), minutes -- defaults to
    notion_tasks.get_task_break_minutes, effort-based) is reserved
    immediately following the task's own slot before the next task is
    considered, so consecutive blocks don't get packed back-to-back with
    no breathing room. The break itself is never turned into a real
    calendar event -- it's just time the next placement skips over, so it
    shows as ordinary free time in Calendar.app, not a separate block.

    `now` (defaults to datetime.now(), computed once here -- not per task,
    so every placement in this run shares one consistent "not before this
    instant" floor) keeps today's slots from starting in the past on a
    mid-day resync -- see _work_blocks_for_day's docstring.

    Tasks are stably re-sorted heavy-before-light (is_light_task()) before
    placement, regardless of the order given -- this guarantees every
    heavy/High-Effort task in the batch has already been attempted before
    any light/Low-Effort one is considered, which is what lets the
    per-day heavy watermark below actually work. Relative order within
    each group (the caller's own Priority/date ranking) is preserved,
    since Python's sort is stable.

    Per-day watermark: once a heavy task is placed on a given day, no
    light task considered for that *same* day may start before that heavy
    task's own end + break -- confirmed 2026-08-03 after a Fill-ins task
    ended up chronologically hours before a same-day Major Projects task,
    just because it happened to fit a small leftover morning gap the
    heavy task couldn't use. This only accounts for heavy tasks placed by
    *this run*, not any pre-existing calendar block from an earlier sync --
    there's no reliable way to infer "was this busy interval a heavy task"
    from a plain calendar event.

    Day-skip guard (2026-08-03, same-day follow-up): now that
    notion_tasks.fetch_actionable_tasks() looks ahead through the end of
    the week instead of only Date <= today, a task can reach this function
    before its own start date arrives. Any `day` earlier than `task.due`
    is skipped for that task -- it's visible for scheduling, but still
    can't be *placed* before its start date.
    """
    start_day = start_day or date.today()
    now = _round_up_to_next(now or datetime.now())
    busy_calendars = busy_calendars or ([calendar_bridge.FOCUS_CALENDAR_NAME] + list(BUSY_CALENDARS))
    duration_fn = duration_fn or get_task_duration_minutes
    break_fn = break_fn or get_task_break_minutes

    tasks = sorted(tasks, key=is_light_task)  # stable: False (heavy) sorts before True (light)

    day_busy_cache: Dict[date, List[Interval]] = {}
    day_provisional: Dict[date, List[Interval]] = {}
    day_heavy_watermark: Dict[date, datetime] = {}

    placements: List[Placement] = []
    unscheduled: List[Task] = []

    for task in tasks:
        duration = timedelta(minutes=duration_fn(task))
        task_is_light = is_light_task(task)
        placed = False
        for offset in range(horizon_days):
            day = start_day + timedelta(days=offset)
            if day.weekday() not in WORKING_WEEKDAYS:
                continue
            # Sunday is light-tasks-only (Quick Wins/Fill-ins) -- confirmed
            # with the user 2026-08-02: Major Projects/Thankless Tasks skip
            # Sunday entirely, regardless of how high-priority or how long
            # they've been eligible, rolling to the next available weekday
            # instead.
            if day.weekday() == SUNDAY and not task_is_light:
                continue
            if day < task.due:
                # Date is the task's *start* date, not a deadline (see
                # notion_tasks.py). fetch_actionable_tasks() now looks ahead
                # through the end of the week, so a task can arrive here
                # before its own start date -- it's visible for scheduling,
                # but still can't be *placed* until that date, so skip
                # forward until `day` reaches it.
                continue
            if day not in day_busy_cache:
                busy_events = calendar_bridge.list_busy_events(datetime.combine(day, time.min), busy_calendars)
                day_busy_cache[day] = [(b.start, b.end) for b in busy_events]
                day_provisional[day] = []

            busy_intervals = day_busy_cache[day] + day_provisional[day]

            floor = now if day == now.date() else None
            if task_is_light and day in day_heavy_watermark:
                watermark = day_heavy_watermark[day]
                floor = max(floor, watermark) if floor else watermark

            free = compute_free_slots(day, busy_intervals, floor=floor)
            fit = next((f for f in free if (f[1] - f[0]) >= duration), None)
            if fit:
                slot_start = fit[0]
                slot_end = slot_start + duration
                placements.append(Placement(task=task, start=slot_start, end=slot_end))
                break_duration = timedelta(minutes=break_fn(task))
                block_end = slot_end + break_duration
                day_provisional[day].append((slot_start, block_end))
                if not task_is_light:
                    day_heavy_watermark[day] = max(day_heavy_watermark.get(day, block_end), block_end)
                placed = True
                break
        if not placed:
            unscheduled.append(task)

    return placements, unscheduled
