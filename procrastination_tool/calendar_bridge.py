"""
AppleScript (osascript) bridge to macOS Calendar.app.

Chosen over PyObjC/EventKit deliberately: recent macOS has a documented
issue where headless processes can't reliably trigger the initial EventKit
permission dialog (see openai/codex#21228). AppleScript's older
Automation/TCC permission model is more battle-tested for background/
launchd use, and reuses the same permission category Mail.app scripting
will need later (Phase 3).

All writes go to a dedicated local calendar (FOCUS_CALENDAR_NAME, default
"Focus Blocks") rather than directly into the Outlook-synced calendar --
still merges into one visible Calendar.app view, but avoids any sync-back
risk to the Exchange server and keeps this tool's writes trivially
clearable (delete the calendar, not individual events) during development.
"""
import subprocess
from datetime import datetime
from typing import List, NamedTuple, Optional, Tuple

from .config import FOCUS_CALENDAR_NAME


class CalendarEvent(NamedTuple):
    uid: str
    summary: str
    start: datetime
    end: datetime
    notes: str


class BusyInterval(NamedTuple):
    start: datetime
    end: datetime
    calendar: str
    summary: str


def _escape_as_string(value: str) -> str:
    # AppleScript string-literal escaping -- backslash first, then quotes.
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _as_multiline_applescript_string(text: str) -> str:
    """
    AppleScript string literals cannot contain a raw embedded newline (unlike
    Python's) -- osascript silently truncates the literal at the first one,
    with no compile error, which is why multi-line event notes (notion_id +
    Priority + Due + url, one per line) previously only ever kept their first
    line once round-tripped. Build the equivalent via `&`-concatenation with
    the `linefeed` constant instead, which AppleScript does support.
    """
    lines = text.split("\n")
    return " & linefeed & ".join(f'"{_escape_as_string(line)}"' for line in lines)


def _run_applescript(script: str, timeout: int = 45) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript failed (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def _parse_records(raw: str, field_count: int) -> List[List[str]]:
    """
    Split AppleScript output produced by list_events()/list_all_events()/
    list_busy_events() into records (RS = ASCII 30) and fields (FS = ASCII
    31) -- see list_events()'s docstring for why control characters rather
    than tab/linefeed. A record that doesn't have exactly field_count
    fields is dropped rather than raising, same defensive behavior all
    three callers already had independently before this was extracted into
    one shared helper.
    """
    records = []
    if raw:
        for line in raw.split("\x1e"):
            if not line:
                continue
            parts = line.split("\x1f")
            if len(parts) == field_count:
                records.append(parts)
    return records


def _as_date_literal(var_name: str, dt: datetime) -> str:
    # Building an AppleScript date via numeric year/month/day/hours/minutes
    # (instead of parsing a string with `date "..."`) is the reliable,
    # locale-independent way to do this -- string-based date parsing in
    # AppleScript depends on the Mac's regional format settings.
    return (
        f"set {var_name} to current date\n"
        f"set year of {var_name} to {dt.year}\n"
        f"set month of {var_name} to {dt.month}\n"
        f"set day of {var_name} to {dt.day}\n"
        f"set hours of {var_name} to {dt.hour}\n"
        f"set minutes of {var_name} to {dt.minute}\n"
        f"set seconds of {var_name} to {dt.second}\n"
    )


def ensure_calendar(name: str = FOCUS_CALENDAR_NAME) -> None:
    """Create the dedicated local calendar if it doesn't already exist."""
    name_esc = _escape_as_string(name)
    script = f'''
    tell application "Calendar"
        if not (exists calendar "{name_esc}") then
            make new calendar with properties {{name:"{name_esc}"}}
        end if
    end tell
    '''
    _run_applescript(script)


def create_event(summary: str, start: datetime, end: datetime,
                  notes: str = "", calendar_name: str = FOCUS_CALENDAR_NAME) -> str:
    """Create an event and return its uid (for later idempotency checks)."""
    ensure_calendar(calendar_name)
    summary_esc = _escape_as_string(summary)
    notes_expr = _as_multiline_applescript_string(notes)
    calendar_esc = _escape_as_string(calendar_name)
    script = (
        _as_date_literal("startDate", start)
        + _as_date_literal("endDate", end)
        + f'''
    tell application "Calendar"
        tell calendar "{calendar_esc}"
            set newEvent to make new event with properties {{summary:"{summary_esc}", start date:startDate, end date:endDate, description:({notes_expr})}}
            return uid of newEvent
        end tell
    end tell
    '''
    )
    return _run_applescript(script)


def list_events(day: datetime, calendar_name: str = FOCUS_CALENDAR_NAME) -> List[CalendarEvent]:
    """List events on `calendar_name` whose start date falls on `day` (local date, time-of-day ignored)."""
    ensure_calendar(calendar_name)
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day.replace(hour=23, minute=59, second=59, microsecond=0)
    calendar_esc = _escape_as_string(calendar_name)
    # Property access on Calendar event objects (start date of e, uid of e,
    # etc.) has to happen *inside* the `tell application "Calendar"` block --
    # doing it after the block closes causes AppleScript to lose track of
    # the property's real type and fail during the ISO-date coercion below
    # with a misleading "Expected end of line but found class name" error.
    # So the whole repeat loop, including string-building, stays nested.
    #
    # Field/record separators are control characters (ASCII 31/30), not
    # tab/linefeed -- event notes are genuinely multi-line (see
    # _as_multiline_applescript_string), so linefeed can't double as the
    # record separator without corrupting the parse.
    script = (
        _as_date_literal("rangeStart", day_start)
        + _as_date_literal("rangeEnd", day_end)
        + f'''
    tell application "Calendar"
        tell calendar "{calendar_esc}"
            set FS to (ASCII character 31)
            set RS to (ASCII character 30)
            set theEvents to every event whose start date is greater than or equal to rangeStart and start date is less than or equal to rangeEnd
            set outputText to ""
            repeat with e in theEvents
                set sd to start date of e
                set ed to end date of e
                set lineText to (uid of e) & FS & (summary of e) & FS & (sd as «class isot» as string) & FS & (ed as «class isot» as string) & FS & (description of e)
                set outputText to outputText & lineText & RS
            end repeat
        end tell
    end tell
    return outputText
    '''
    )
    raw = _run_applescript(script)
    events = []
    for uid, summary, start_s, end_s, notes in _parse_records(raw, 5):
        events.append(CalendarEvent(
            uid=uid, summary=summary,
            start=datetime.fromisoformat(start_s),
            end=datetime.fromisoformat(end_s),
            notes=notes,
        ))
    return events


def list_all_events(calendar_name: str = FOCUS_CALENDAR_NAME) -> List[CalendarEvent]:
    """
    Every event in `calendar_name`, with no date bound -- used for
    reconciling this tool's own blocks against Notion (sync.py), where a
    task's due date may have drifted since it was scheduled, so scoping to
    "today" or "this week" could miss stale blocks entirely. Safe to
    enumerate without a bound because this calendar only ever contains
    what this tool itself created.
    """
    ensure_calendar(calendar_name)
    calendar_esc = _escape_as_string(calendar_name)
    script = f'''
    tell application "Calendar"
        tell calendar "{calendar_esc}"
            set FS to (ASCII character 31)
            set RS to (ASCII character 30)
            set theEvents to every event
            set outputText to ""
            repeat with e in theEvents
                set sd to start date of e
                set ed to end date of e
                set lineText to (uid of e) & FS & (summary of e) & FS & (sd as «class isot» as string) & FS & (ed as «class isot» as string) & FS & (description of e)
                set outputText to outputText & lineText & RS
            end repeat
        end tell
    end tell
    return outputText
    '''
    raw = _run_applescript(script)
    events = []
    for uid, summary, start_s, end_s, notes in _parse_records(raw, 5):
        events.append(CalendarEvent(
            uid=uid, summary=summary,
            start=datetime.fromisoformat(start_s),
            end=datetime.fromisoformat(end_s),
            notes=notes,
        ))
    return events


def list_busy_events(day: datetime, calendar_names: List[str]) -> List[BusyInterval]:
    """
    List events on `day` across several existing calendars, merged into one
    list -- used for free-slot computation, not just the Focus Blocks
    calendar this tool writes to. Unlike list_events()/ensure_calendar(),
    this does NOT create missing calendars: these are calendars the user
    already has (e.g. their Outlook-synced one), so a typo'd name should
    surface as a clear AppleScript error, not silently produce an empty
    result from a freshly created blank calendar.

    **Known latency, investigated 2026-08-03, not fully solvable from this
    side**: AppleScript's `whose` filter on Calendar.app events scans a
    calendar's entire event history linearly rather than using a date
    index, so an iCloud-synced calendar with years of accumulated events
    (confirmed: one such calendar alone consistently took ~15s) makes this
    call slow. **Running each calendar's query as a separate concurrent
    subprocess was tried and measured to make no difference** -- two
    concurrent `osascript` calls to different calendars were confirmed (via
    direct timing) to finish sequentially, one visibly queued behind the
    other's actual work, not overlapping -- because Calendar.app itself
    serializes incoming Apple Events one at a time regardless of how many
    client processes are asking concurrently. The bottleneck is inside
    Calendar.app, not in this process, so no amount of Python-side
    concurrency can shorten it; reverted to the simpler single-script,
    single-subprocess form. The only real mitigation available here is
    `_run_applescript`'s timeout, bumped from 30s to 45s after the combined
    4-calendar query was measured taking ~29.6s against this user's real
    calendars -- comfortable headroom now, revisit if it grows further
    (e.g. as 个人/PQi/iCloud-work accumulate more events over time).
    """
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day.replace(hour=23, minute=59, second=59, microsecond=0)

    cal_list_literal = ", ".join(f'"{_escape_as_string(n)}"' for n in calendar_names)
    script = (
        _as_date_literal("rangeStart", day_start)
        + _as_date_literal("rangeEnd", day_end)
        + f'''
    set calNames to {{{cal_list_literal}}}
    set FS to (ASCII character 31)
    set RS to (ASCII character 30)
    set outputText to ""
    tell application "Calendar"
        repeat with calName in calNames
            tell calendar calName
                set theEvents to every event whose start date is greater than or equal to rangeStart and start date is less than or equal to rangeEnd
                repeat with e in theEvents
                    set sd to start date of e
                    set ed to end date of e
                    set lineText to calName & FS & (summary of e) & FS & (sd as «class isot» as string) & FS & (ed as «class isot» as string)
                    set outputText to outputText & lineText & RS
                end repeat
            end tell
        end repeat
    end tell
    return outputText
    '''
    )
    raw = _run_applescript(script)
    intervals = []
    for cal_name, summary, start_s, end_s in _parse_records(raw, 4):
        intervals.append(BusyInterval(
            start=datetime.fromisoformat(start_s),
            end=datetime.fromisoformat(end_s),
            calendar=cal_name, summary=summary,
        ))
    return intervals


def find_event_by_notion_id(notion_id: str, calendar_name: str = FOCUS_CALENDAR_NAME) -> Optional[str]:
    """
    Look up an existing Focus Blocks event whose description was tagged
    with this Notion page ID (see sync_tasks.py's NOTION_ID_TAG format).
    Returns the event's uid if found, else None. Used to make the daily
    sync idempotent -- a task already represented by a calendar block
    shouldn't get a second one on rerun.
    """
    ensure_calendar(calendar_name)
    id_esc = _escape_as_string(notion_id)
    calendar_esc = _escape_as_string(calendar_name)
    script = f'''
    tell application "Calendar"
        tell calendar "{calendar_esc}"
            set matches to (every event whose description contains "{id_esc}")
            if (count of matches) > 0 then
                return uid of (item 1 of matches)
            else
                return ""
            end if
        end tell
    end tell
    '''
    result = _run_applescript(script)
    return result if result else None


def delete_event_by_uid(uid: str, calendar_name: str = FOCUS_CALENDAR_NAME) -> bool:
    """Delete an event by uid. Returns True if something was deleted."""
    uid_esc = _escape_as_string(uid)
    calendar_esc = _escape_as_string(calendar_name)
    script = f'''
    tell application "Calendar"
        tell calendar "{calendar_esc}"
            set matches to (every event whose uid is "{uid_esc}")
            set n to count of matches
            delete matches
            return n
        end tell
    end tell
    '''
    result = _run_applescript(script)
    return result not in ("", "0")
