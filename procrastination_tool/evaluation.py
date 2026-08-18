"""
End-of-day evaluation + mood tracker (3/3.1/3.2 in the redesign plan).
Same hand-rolled-SQLite, guarded-CREATE-TABLE pattern as character.py/
bloodstain.py -- all state lives in the existing data/sessions.db.

Two tables:
- `mood_entries` -- logged any time during the day (not just at evaluation
  time), a simple 1-5 score + optional free-text note.
- `daily_evaluations` -- a persisted snapshot, written each time
  generate_daily_evaluation() runs (the "Generate today's evaluation"
  button), so history survives even as the underlying sessions/tasks data
  keeps changing after the fact. Re-running it for the same date
  overwrites that date's row (UPSERT) rather than duplicating -- the
  button is meant to be pressable more than once in a day.

Multi-user follow-up: `mood_entries` gained a plain `user_id` column
(simple additive ALTER TABLE). `daily_evaluations`/`weekly_retros` each
had a bare `date`/`week_start` TEXT PRIMARY KEY -- two users generating an
evaluation for the same calendar date (or retro for the same week) would
otherwise collide and overwrite each other's row, so both primary keys
became composite (`user_id`, date/week_start). That's a constraint change
ALTER TABLE can't make in place; scripts/bootstrap_multiuser.py rebuilds
both tables for the real, already-populated data/sessions.db.
"""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from . import tasks
from .config import SESSION_DB_PATH
from .weekly import week_bounds, week_start_date

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mood_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    mood_score INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS daily_evaluations (
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    sessions_count INTEGER NOT NULL,
    focused_minutes REAL NOT NULL,
    completion_rate REAL,
    tasks_completed_count INTEGER NOT NULL,
    runes_earned INTEGER NOT NULL,
    mood_avg REAL,
    summary_json TEXT NOT NULL,
    PRIMARY KEY (user_id, date)
);
CREATE TABLE IF NOT EXISTS weekly_retros (
    user_id INTEGER NOT NULL,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    sessions_count INTEGER NOT NULL,
    focused_minutes REAL NOT NULL,
    tasks_completed_count INTEGER NOT NULL,
    committed_count INTEGER NOT NULL,
    committed_completed_count INTEGER NOT NULL,
    mood_avg REAL,
    summary_json TEXT NOT NULL,
    PRIMARY KEY (user_id, week_start)
);
"""

# Nullable for the same reason every other module's multi-user column is:
# ALTER TABLE can't add NOT NULL with no default to a table that already
# has rows. scripts/bootstrap_multiuser.py backfills existing NULL rows to
# the owner's account.
_NEW_COLUMNS = {"user_id": "INTEGER"}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(mood_entries)")}
    for name, coltype in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE mood_entries ADD COLUMN {name} {coltype}")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn


def _quadrant_label(priority: str) -> str:
    # Mirrors frontend/src/api/types.ts's quadrantLabel() -- "Quick Wins
    # (High Impact-Low Effort)" -> "Quick Wins". Kept as a tiny local
    # helper rather than a shared module since this is the only Python
    # call site.
    return priority.split(" (")[0]


@dataclass
class MoodEntry:
    id: int
    ts: datetime
    mood_score: int
    note: str


def _row_to_mood(row: sqlite3.Row) -> MoodEntry:
    return MoodEntry(
        id=row["id"], ts=datetime.fromisoformat(row["ts"]),
        mood_score=row["mood_score"], note=row["note"],
    )


def log_mood(user_id: int, score: int, note: str = "") -> MoodEntry:
    if not 1 <= score <= 5:
        raise ValueError("mood_score must be between 1 and 5")
    ts = datetime.now()
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO mood_entries (user_id, ts, mood_score, note) VALUES (?, ?, ?, ?)",
            (user_id, ts.isoformat(), score, note),
        )
        conn.commit()
        entry_id = cur.lastrowid
    return MoodEntry(id=entry_id, ts=ts, mood_score=score, note=note)


def list_mood_entries(user_id: int, day: Optional[date_cls] = None) -> List[MoodEntry]:
    """Every mood entry `user_id` logged on `day` (local date), or their
    most recent 100 across all time if `day` is None."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        if day is not None:
            start = datetime.combine(day, datetime.min.time())
            end = start + timedelta(days=1)
            rows = conn.execute(
                "SELECT * FROM mood_entries WHERE user_id = ? AND ts >= ? AND ts < ? ORDER BY ts",
                (user_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM mood_entries WHERE user_id = ? ORDER BY ts DESC LIMIT 100",
                (user_id,),
            ).fetchall()
    return [_row_to_mood(r) for r in rows]


@dataclass
class DailyEvaluation:
    date: date_cls
    generated_at: datetime
    sessions_count: int
    focused_minutes: float
    completion_rate: Optional[float]
    tasks_completed_count: int
    runes_earned: int
    mood_avg: Optional[float]
    mood_entries: List[MoodEntry] = field(default_factory=list)
    tasks_completed_names: List[str] = field(default_factory=list)
    quadrant_breakdown: Dict[str, int] = field(default_factory=dict)


def generate_daily_evaluation(user_id: int, day: Optional[date_cls] = None) -> DailyEvaluation:
    """Compute and persist (UPSERT) the evaluation snapshot for `user_id`
    on `day` (defaults to today). Reuses the same session-stats windowing
    logic as api/routers/sessions.py's get_stats, scoped to one calendar
    day instead of a rolling N-day window."""
    day = day or date_cls.today()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)

    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        session_rows = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND start_time >= ? AND start_time < ?",
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchall()

    sessions_count = len(session_rows)
    completed_rows = [r for r in session_rows if r["completed"]]
    completion_rate = (len(completed_rows) / sessions_count) if sessions_count else None
    focused_minutes = sum(r["actual_minutes"] for r in completed_rows)
    runes_earned = sum(r["runes_awarded"] or 0 for r in session_rows)

    completed_today = [
        t for t in tasks.list_all_tasks(user_id)
        if t.completed_at is not None and start <= t.completed_at < end
    ]
    quadrant_breakdown: Dict[str, int] = {}
    for t in completed_today:
        label = _quadrant_label(t.priority)
        quadrant_breakdown[label] = quadrant_breakdown.get(label, 0) + 1

    mood_entries = list_mood_entries(user_id, day)
    mood_avg = (
        sum(m.mood_score for m in mood_entries) / len(mood_entries) if mood_entries else None
    )

    generated_at = datetime.now()
    summary = {
        "tasks_completed_names": [t.name for t in completed_today],
        "quadrant_breakdown": quadrant_breakdown,
    }

    with closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO daily_evaluations
                (user_id, date, generated_at, sessions_count, focused_minutes, completion_rate,
                 tasks_completed_count, runes_earned, mood_avg, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                generated_at = excluded.generated_at,
                sessions_count = excluded.sessions_count,
                focused_minutes = excluded.focused_minutes,
                completion_rate = excluded.completion_rate,
                tasks_completed_count = excluded.tasks_completed_count,
                runes_earned = excluded.runes_earned,
                mood_avg = excluded.mood_avg,
                summary_json = excluded.summary_json
            """,
            (
                user_id, day.isoformat(), generated_at.isoformat(), sessions_count,
                focused_minutes, completion_rate, len(completed_today), runes_earned, mood_avg,
                json.dumps(summary),
            ),
        )
        conn.commit()

    return DailyEvaluation(
        date=day, generated_at=generated_at, sessions_count=sessions_count,
        focused_minutes=focused_minutes, completion_rate=completion_rate,
        tasks_completed_count=len(completed_today), runes_earned=runes_earned,
        mood_avg=mood_avg, mood_entries=mood_entries,
        tasks_completed_names=[t.name for t in completed_today],
        quadrant_breakdown=quadrant_breakdown,
    )


def _row_to_evaluation(user_id: int, row: sqlite3.Row) -> DailyEvaluation:
    day = date_cls.fromisoformat(row["date"])
    summary = json.loads(row["summary_json"])
    return DailyEvaluation(
        date=day, generated_at=datetime.fromisoformat(row["generated_at"]),
        sessions_count=row["sessions_count"], focused_minutes=row["focused_minutes"],
        completion_rate=row["completion_rate"], tasks_completed_count=row["tasks_completed_count"],
        runes_earned=row["runes_earned"], mood_avg=row["mood_avg"],
        mood_entries=list_mood_entries(user_id, day),
        tasks_completed_names=summary.get("tasks_completed_names", []),
        quadrant_breakdown=summary.get("quadrant_breakdown", {}),
    )


def get_evaluation(user_id: int, day: date_cls) -> Optional[DailyEvaluation]:
    """The persisted snapshot for `user_id` on `day`, if one has been
    generated."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM daily_evaluations WHERE user_id = ? AND date = ?",
            (user_id, day.isoformat()),
        ).fetchone()
    return _row_to_evaluation(user_id, row) if row else None


def list_evaluations(user_id: int, days: int = 7) -> List[DailyEvaluation]:
    """The most recent `days` persisted snapshots for `user_id`, most
    recent first -- used for the frontend's short mood/focus trend view.
    Only returns dates that actually have a generated evaluation (no
    gap-filling)."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM daily_evaluations WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, days),
        ).fetchall()
    return [_row_to_evaluation(user_id, r) for r in rows]


def has_logged_today(user_id: int, day: Optional[date_cls] = None) -> bool:
    """True if `user_id` already has a mood entry or a generated
    evaluation snapshot for `day` (default today) -- the sole signal the
    end-of-day reminder banner uses to decide whether to show itself."""
    day = day or date_cls.today()
    return bool(list_mood_entries(user_id, day)) or get_evaluation(user_id, day) is not None


@dataclass
class WeeklyRetro:
    week_start: date_cls
    week_end: date_cls
    generated_at: datetime
    sessions_count: int
    focused_minutes: float
    tasks_completed_count: int
    committed_count: int
    committed_completed_count: int
    mood_avg: Optional[float]
    tasks_completed_names: List[str] = field(default_factory=list)
    quadrant_breakdown: Dict[str, int] = field(default_factory=dict)


def generate_weekly_retro(user_id: int, week_start: Optional[date_cls] = None) -> WeeklyRetro:
    """Compute and persist (UPSERT) the retro for `user_id` for the week
    containing `week_start` (defaults to the current week). Sessions/
    focused_minutes/mood are queried directly from `sessions`/
    `mood_entries`, windowed to the week -- not summed from
    daily_evaluations rows -- so this doesn't depend on every day having
    had a daily evaluation generated (see generate_daily_evaluation's
    identical windowing idiom). Committed vs. completed: tasks whose
    week_committed_date is this week's Monday, split by whether
    completed_at also falls inside this week."""
    week_start = week_start_date(week_start or date_cls.today())
    _, week_end = week_bounds(week_start)
    start = datetime.combine(week_start, datetime.min.time())
    end = datetime.combine(week_end, datetime.min.time()) + timedelta(days=1)

    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        session_rows = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND start_time >= ? AND start_time < ?",
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        mood_rows = conn.execute(
            "SELECT mood_score FROM mood_entries WHERE user_id = ? AND ts >= ? AND ts < ?",
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchall()

    sessions_count = len(session_rows)
    completed_rows = [r for r in session_rows if r["completed"]]
    focused_minutes = sum(r["actual_minutes"] for r in completed_rows)

    all_tasks = tasks.list_all_tasks(user_id)
    completed_this_week = [
        t for t in all_tasks
        if t.completed_at is not None and start <= t.completed_at < end
    ]
    quadrant_breakdown: Dict[str, int] = {}
    for t in completed_this_week:
        label = _quadrant_label(t.priority)
        quadrant_breakdown[label] = quadrant_breakdown.get(label, 0) + 1

    committed = [t for t in all_tasks if t.week_committed_date == week_start.isoformat()]
    committed_completed = [
        t for t in committed
        if t.completed_at is not None and start <= t.completed_at < end
    ]

    mood_avg = (
        sum(r["mood_score"] for r in mood_rows) / len(mood_rows) if mood_rows else None
    )

    generated_at = datetime.now()
    summary = {
        "tasks_completed_names": [t.name for t in completed_this_week],
        "quadrant_breakdown": quadrant_breakdown,
    }

    with closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO weekly_retros
                (user_id, week_start, week_end, generated_at, sessions_count, focused_minutes,
                 tasks_completed_count, committed_count, committed_completed_count,
                 mood_avg, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, week_start) DO UPDATE SET
                week_end = excluded.week_end,
                generated_at = excluded.generated_at,
                sessions_count = excluded.sessions_count,
                focused_minutes = excluded.focused_minutes,
                tasks_completed_count = excluded.tasks_completed_count,
                committed_count = excluded.committed_count,
                committed_completed_count = excluded.committed_completed_count,
                mood_avg = excluded.mood_avg,
                summary_json = excluded.summary_json
            """,
            (
                user_id, week_start.isoformat(), week_end.isoformat(), generated_at.isoformat(),
                sessions_count, focused_minutes, len(completed_this_week),
                len(committed), len(committed_completed), mood_avg, json.dumps(summary),
            ),
        )
        conn.commit()

    return WeeklyRetro(
        week_start=week_start, week_end=week_end, generated_at=generated_at,
        sessions_count=sessions_count, focused_minutes=focused_minutes,
        tasks_completed_count=len(completed_this_week), committed_count=len(committed),
        committed_completed_count=len(committed_completed), mood_avg=mood_avg,
        tasks_completed_names=[t.name for t in completed_this_week],
        quadrant_breakdown=quadrant_breakdown,
    )


def _row_to_weekly_retro(row: sqlite3.Row) -> WeeklyRetro:
    summary = json.loads(row["summary_json"])
    return WeeklyRetro(
        week_start=date_cls.fromisoformat(row["week_start"]),
        week_end=date_cls.fromisoformat(row["week_end"]),
        generated_at=datetime.fromisoformat(row["generated_at"]),
        sessions_count=row["sessions_count"], focused_minutes=row["focused_minutes"],
        tasks_completed_count=row["tasks_completed_count"],
        committed_count=row["committed_count"],
        committed_completed_count=row["committed_completed_count"],
        mood_avg=row["mood_avg"],
        tasks_completed_names=summary.get("tasks_completed_names", []),
        quadrant_breakdown=summary.get("quadrant_breakdown", {}),
    )


def get_weekly_retro(user_id: int, week_start: date_cls) -> Optional[WeeklyRetro]:
    """The persisted retro for `user_id` for the week starting
    `week_start` (must be a Monday), if one has been generated."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM weekly_retros WHERE user_id = ? AND week_start = ?",
            (user_id, week_start.isoformat()),
        ).fetchone()
    return _row_to_weekly_retro(row) if row else None


def list_weekly_retros(user_id: int, weeks: int = 6) -> List[WeeklyRetro]:
    """The most recent `weeks` persisted retros for `user_id`, most recent
    first -- used for the velocity trend. Only returns weeks that
    actually have a generated retro (no gap-filling), same convention as
    list_evaluations."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM weekly_retros WHERE user_id = ? ORDER BY week_start DESC LIMIT ?",
            (user_id, weeks),
        ).fetchall()
    return [_row_to_weekly_retro(r) for r in rows]
