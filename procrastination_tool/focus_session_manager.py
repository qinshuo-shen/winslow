"""
Browser-drivable focus session state machine (Phase 5, web migration).

focus_timer.py's own blocking loop (_run_interactive/_run_noninteractive)
is a foreground terminal read-eval loop -- it owns the process until the
session ends. A browser can't block like that: the frontend needs to
start a session, then poll it, possibly close the tab and come back, and
still see accurate state. This module is that alternative: a singleton,
lock-guarded state machine driven by explicit start/pause/resume/stop
calls plus a periodic tick() (see api/main.py's lifespan background task),
rather than one function that owns the clock for the session's duration.

time.monotonic() (not datetime.now()) drives all elapsed-time math, same
choice focus_timer.py's own _run_interactive loop makes and for the same
reason -- monotonic time can't jump backwards/forwards under wall-clock
adjustments (DST, NTP sync, etc.), only real elapsed time matters here.
`start_time` is still recorded via datetime.now() purely for logging
(SessionResult/log_session want a real timestamp, not a monotonic one).

Once a session ends (completed, stopped early, or pause-timeout failed),
all of the actual reward/bloodstain/questline/notification/DB-log work is
delegated to focus_timer.finalize_session() -- the same function
run_focus_session() (the CLI path) now also calls. That's the whole point
of Phase 5's focus_timer.py refactor: this manager and the CLI share one
"what happens when a session ends" implementation, they just differ in
how they drive a session to that end.
"""
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from . import focus_timer
from .config import PAUSE_FAIL_MINUTES


@dataclass
class FocusSessionState:
    status: str = "idle"  # "idle" | "running" | "paused"
    start_time: Optional[datetime] = None
    duration_minutes: float = 0.0
    task_label: Optional[str] = None
    priority: Optional[str] = None
    specific_project: Optional[str] = None
    worked_seconds: float = 0.0        # accumulated BEFORE the current running stretch
    running_since: Optional[float] = None   # time.monotonic(), set only while status == "running"
    paused_since: Optional[float] = None    # time.monotonic(), set only while status == "paused"
    last_result: Optional[focus_timer.SessionResult] = None  # most recent finished session, until next start()


class FocusSessionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = FocusSessionState()

    def start(self, duration_minutes, task_label, priority, specific_project) -> FocusSessionState:
        with self._lock:
            if self._state.status != "idle":
                raise ValueError("A session is already running or paused")
            self._state = FocusSessionState(
                status="running", start_time=datetime.now(), duration_minutes=duration_minutes,
                task_label=task_label, priority=priority, specific_project=specific_project,
                running_since=time.monotonic(),
            )
            return self._state

    def pause(self) -> FocusSessionState:
        with self._lock:
            if self._state.status != "running":
                raise ValueError("No running session to pause")
            now = time.monotonic()
            self._state.worked_seconds += now - self._state.running_since
            self._state.running_since = None
            self._state.paused_since = now
            self._state.status = "paused"
            return self._state

    def resume(self) -> FocusSessionState:
        with self._lock:
            if self._state.status != "paused":
                raise ValueError("No paused session to resume")
            self._state.paused_since = None
            self._state.running_since = time.monotonic()
            self._state.status = "running"
            return self._state

    def stop(self) -> focus_timer.SessionResult:
        with self._lock:
            if self._state.status == "idle":
                raise ValueError("No active session to stop")
            worked = self._current_worked_seconds_locked()
            return self._finalize_locked(worked, focus_timer.OUTCOME_STOPPED_EARLY)

    def tick(self) -> None:
        """Call periodically (background loop) AND inline before returning
        state to a client, so state is never more than ~1s stale either
        way. Do NOT call this while already holding the lock (e.g. don't
        call it from inside snapshot()) -- threading.Lock is not
        reentrant."""
        with self._lock:
            if self._state.status == "running":
                worked = self._current_worked_seconds_locked()
                if worked >= self._state.duration_minutes * 60:
                    self._finalize_locked(self._state.duration_minutes * 60, focus_timer.OUTCOME_COMPLETED)
            elif self._state.status == "paused":
                paused_for = time.monotonic() - self._state.paused_since
                if paused_for >= PAUSE_FAIL_MINUTES * 60:
                    self._finalize_locked(self._state.worked_seconds, focus_timer.OUTCOME_FAILED_PAUSE_TIMEOUT)

    def _current_worked_seconds_locked(self) -> float:
        s = self._state
        if s.status == "running":
            return s.worked_seconds + (time.monotonic() - s.running_since)
        return s.worked_seconds

    def _finalize_locked(self, worked_seconds: float, outcome: str) -> focus_timer.SessionResult:
        # Called only while self._lock is already held. Blocking I/O
        # (sqlite + osascript notification) happens here; that's fine --
        # this manager already lives off the asyncio event loop (see
        # api/main.py's lifespan task, which wraps tick() in
        # asyncio.to_thread), so briefly blocking other manager calls for
        # the duration of one finalize is an acceptable trade for a
        # single-user localhost app, not worth engineering around.
        s = self._state
        end = datetime.now()
        result = focus_timer.finalize_session(
            s.start_time, end, s.duration_minutes, worked_seconds, outcome,
            s.task_label, s.priority, s.specific_project,
        )
        self._state = FocusSessionState(status="idle", last_result=result)
        return result

    def snapshot(self) -> FocusSessionState:
        with self._lock:
            return self._state


manager = FocusSessionManager()
