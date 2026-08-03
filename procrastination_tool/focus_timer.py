"""
Self-reported Pomodoro-style focus timer (Phase 2). Deliberately NOT
active-window/app monitoring -- the user explicitly chose self-reported
timing over surveillance when this was planned. A session is just: you
run it, you either let it finish, Ctrl-C out early, or pause/resume it
(see below), and it gets logged.

Single blocking foreground command (not separate start/stop invocations)
-- simpler, and avoids needing a state file to track "is a session
currently running" across separate process invocations. Ctrl-C in the
same terminal is how you end a session early.

Reward (the spin wheel) only fires on a FULLY completed session -- not an
early Ctrl-C stop, and not an auto-failed pause timeout (see below) --
keeps the incentive aligned with actually finishing the session rather
than rewarding any attempt.

Pause/resume (2026-08-03 follow-up): press 'p' to pause, 'r' to resume --
a real interruption (a phone call, someone at the door) shouldn't force
you to either abandon the session entirely or leave the clock running
unattended. Implemented via termios/tty.setcbreak + select.select for
non-blocking single-keypress polling -- this project is macOS-only (see
calendar_bridge.py's osascript use elsewhere), so no cross-platform input
shim is needed. cbreak mode only clears ICANON/ECHO, not ISIG, so Ctrl-C
still raises KeyboardInterrupt exactly as before.

If a pause lasts longer than config.PAUSE_FAIL_MINUTES (default 20), the
session auto-fails: no reward, logged with a distinct outcome. This is
measured from the CURRENT, unbroken pause only (confirmed with the
user) -- it resets to zero on every resume, it does not accumulate across
a session's multiple pause/resume cycles.

Time spent paused doesn't count toward a session's logged minutes
(confirmed with the user) -- `actual_minutes` is worked time only, not
wall-clock start-to-end, so a 25-min session paused for 5 min still logs
as 25 worked minutes even though 30 min passed in the real world.
"""
import select
import sqlite3
import sys
import termios
import time
import tty
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from . import notify, spin_wheel
from .config import FOCUS_SESSION_MINUTES, PAUSE_FAIL_MINUTES, SESSION_DB_PATH

OUTCOME_COMPLETED = "completed"
OUTCOME_STOPPED_EARLY = "stopped_early"
OUTCOME_FAILED_PAUSE_TIMEOUT = "failed_pause_timeout"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    planned_minutes REAL NOT NULL,
    actual_minutes REAL NOT NULL,
    completed INTEGER NOT NULL,
    task_label TEXT,
    wheel_result TEXT
)
"""


@dataclass
class SessionResult:
    completed: bool
    actual_minutes: float
    wheel_result: Optional[str]
    outcome: str = OUTCOME_COMPLETED


@dataclass
class SessionRow:
    id: int
    start_time: datetime
    end_time: datetime
    planned_minutes: float
    actual_minutes: float
    completed: bool
    task_label: Optional[str]
    wheel_result: Optional[str]
    outcome: Optional[str]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute(_SCHEMA)
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN outcome TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists -- sqlite has no ADD COLUMN IF NOT EXISTS
    return conn


def log_session(start: datetime, end: datetime, planned_minutes: float, actual_minutes: float,
                 outcome: str, task_label: Optional[str], wheel_result: Optional[str]) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO sessions (start_time, end_time, planned_minutes, actual_minutes, "
            "completed, task_label, wheel_result, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (start.isoformat(), end.isoformat(), planned_minutes, actual_minutes,
             int(outcome == OUTCOME_COMPLETED), task_label, wheel_result, outcome),
        )
        conn.commit()


def get_recent_sessions(limit: int = 10) -> List[SessionRow]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        SessionRow(
            id=r["id"], start_time=datetime.fromisoformat(r["start_time"]),
            end_time=datetime.fromisoformat(r["end_time"]), planned_minutes=r["planned_minutes"],
            actual_minutes=r["actual_minutes"], completed=bool(r["completed"]),
            task_label=r["task_label"], wheel_result=r["wheel_result"],
            outcome=r["outcome"],
        )
        for r in rows
    ]


def _format_mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _read_key(timeout: float) -> Optional[str]:
    """Non-blocking single-char read from stdin; None if nothing arrived within `timeout` seconds."""
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    return sys.stdin.read(1) if ready else None


def _run_interactive(duration_minutes: float) -> Tuple[str, float]:
    """
    The real pause-capable loop -- stdin is put into cbreak mode so 'p'/'r'
    can be read one keypress at a time without waiting for Enter. Returns
    (outcome, worked_seconds). Only called when stdin is a real terminal
    (see run_focus_session): cbreak mode and Ctrl-C-as-KeyboardInterrupt
    both depend on that.
    """
    total_seconds = duration_minutes * 60
    outcome = OUTCOME_COMPLETED
    worked_seconds = 0.0
    paused = False
    pause_started_at: Optional[float] = None

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        last_tick = time.monotonic()
        try:
            while worked_seconds < total_seconds:
                key = _read_key(timeout=0.3)
                now = time.monotonic()
                dt = now - last_tick
                last_tick = now

                if key == "p" and not paused:
                    paused = True
                    pause_started_at = now
                    print("\n  Paused. Press 'r' to resume "
                          f"(auto-fails after {PAUSE_FAIL_MINUTES:g} min paused).")
                    continue
                if key == "r" and paused:
                    paused = False
                    pause_started_at = None
                    print("\n  Resumed.")
                    continue

                if paused:
                    paused_for = now - pause_started_at
                    if paused_for >= PAUSE_FAIL_MINUTES * 60:
                        outcome = OUTCOME_FAILED_PAUSE_TIMEOUT
                        print(f"\n  Session failed -- paused for over {PAUSE_FAIL_MINUTES:g} min.")
                        break
                    remaining_before_fail = PAUSE_FAIL_MINUTES * 60 - paused_for
                    print(f"\r  PAUSED -- auto-fails in {_format_mmss(remaining_before_fail)}   ",
                          end="", flush=True)
                else:
                    worked_seconds = min(total_seconds, worked_seconds + dt)
                    remaining = total_seconds - worked_seconds
                    print(f"\r  {_format_mmss(remaining)} remaining        ", end="", flush=True)
            else:
                print(f"\r  {_format_mmss(0)} remaining        ")
        except KeyboardInterrupt:
            outcome = OUTCOME_STOPPED_EARLY
            print("\n  Stopped early.")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return outcome, worked_seconds


def _run_noninteractive(duration_minutes: float) -> Tuple[str, float]:
    """
    Fallback for when stdin isn't a real terminal (e.g. redirected input)
    -- no pause capability, matches this module's pre-pause/resume
    behavior. Nothing in this codebase currently calls run_focus_session()
    this way (only focus_cli.py's interactive `focus start`), but a
    session shouldn't hang or error out if it ever is.
    """
    total_seconds = duration_minutes * 60
    outcome = OUTCOME_COMPLETED
    elapsed = 0.0
    try:
        while elapsed < total_seconds:
            remaining = total_seconds - elapsed
            print(f"\r  {_format_mmss(remaining)} remaining", end="", flush=True)
            tick = min(1.0, remaining)
            time.sleep(tick)
            elapsed += tick
        print(f"\r  {_format_mmss(0)} remaining")
    except KeyboardInterrupt:
        outcome = OUTCOME_STOPPED_EARLY
        print("\n  Stopped early.")
    return outcome, elapsed


def run_focus_session(duration_minutes: float = FOCUS_SESSION_MINUTES,
                       task_label: Optional[str] = None) -> SessionResult:
    start = datetime.now()
    label_suffix = f" on {task_label!r}" if task_label else ""

    if sys.stdin.isatty():
        print(f"Focus session started{label_suffix} -- {duration_minutes:g} min. "
              "Ctrl-C to stop early, 'p' to pause, 'r' to resume.")
        outcome, worked_seconds = _run_interactive(duration_minutes)
    else:
        print(f"Focus session started{label_suffix} -- {duration_minutes:g} min. "
              "Ctrl-C to stop early. (stdin isn't a terminal -- pause/resume unavailable.)")
        outcome, worked_seconds = _run_noninteractive(duration_minutes)

    end = datetime.now()
    actual_minutes = worked_seconds / 60

    wheel_result = None
    if outcome == OUTCOME_COMPLETED:
        wheel_result = spin_wheel.spin()
        print(f"\nSession complete! Your reward: {wheel_result}")
        notify.send_notification("Focus session complete", wheel_result, subtitle="Nice work!")
    elif outcome == OUTCOME_FAILED_PAUSE_TIMEOUT:
        print(f"Logged {actual_minutes:.1f} min worked -- paused too long, session failed (no reward).")
        notify.send_notification(
            "Focus session failed",
            f"Paused over {PAUSE_FAIL_MINUTES:g} min -- no reward",
            subtitle=f"{actual_minutes:.1f} min logged",
        )
    else:
        print(f"Logged {actual_minutes:.1f} min (incomplete, no reward this time).")
        notify.send_notification("Focus session ended early", f"{actual_minutes:.1f} min logged")

    log_session(start, end, duration_minutes, actual_minutes, outcome, task_label, wheel_result)
    return SessionResult(completed=(outcome == OUTCOME_COMPLETED), actual_minutes=actual_minutes,
                          wheel_result=wheel_result, outcome=outcome)
