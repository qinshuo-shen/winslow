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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mood_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    mood_score INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS daily_evaluations (
    date TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    sessions_count INTEGER NOT NULL,
    focused_minutes REAL NOT NULL,
    completion_rate REAL,
    tasks_completed_count INTEGER NOT NULL,
    runes_earned INTEGER NOT NULL,
    mood_avg REAL,
    summary_json TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
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


def log_mood(score: int, note: str = "") -> MoodEntry:
    if not 1 <= score <= 5:
        raise ValueError("mood_score must be between 1 and 5")
    ts = datetime.now()
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO mood_entries (ts, mood_score, note) VALUES (?, ?, ?)",
            (ts.isoformat(), score, note),
        )
        conn.commit()
        entry_id = cur.lastrowid
    return MoodEntry(id=entry_id, ts=ts, mood_score=score, note=note)


def list_mood_entries(day: Optional[date_cls] = None) -> List[MoodEntry]:
    """Every mood entry on `day` (local date), or the most recent 100
    across all time if `day` is None."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        if day is not None:
            start = datetime.combine(day, datetime.min.time())
            end = start + timedelta(days=1)
            rows = conn.execute(
                "SELECT * FROM mood_entries WHERE ts >= ? AND ts < ? ORDER BY ts",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM mood_entries ORDER BY ts DESC LIMIT 100"
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


def generate_daily_evaluation(day: Optional[date_cls] = None) -> DailyEvaluation:
    """Compute and persist (UPSERT) the evaluation snapshot for `day`
    (defaults to today). Reuses the same session-stats windowing logic as
    api/routers/sessions.py's get_stats, scoped to one calendar day instead
    of a rolling N-day window."""
    day = day or date_cls.today()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)

    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        session_rows = conn.execute(
            "SELECT * FROM sessions WHERE start_time >= ? AND start_time < ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    sessions_count = len(session_rows)
    completed_rows = [r for r in session_rows if r["completed"]]
    completion_rate = (len(completed_rows) / sessions_count) if sessions_count else None
    focused_minutes = sum(r["actual_minutes"] for r in completed_rows)
    runes_earned = sum(r["runes_awarded"] or 0 for r in session_rows)

    completed_today = [
        t for t in tasks.list_all_tasks()
        if t.completed_at is not None and start <= t.completed_at < end
    ]
    quadrant_breakdown: Dict[str, int] = {}
    for t in completed_today:
        label = _quadrant_label(t.priority)
        quadrant_breakdown[label] = quadrant_breakdown.get(label, 0) + 1

    mood_entries = list_mood_entries(day)
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
                (date, generated_at, sessions_count, focused_minutes, completion_rate,
                 tasks_completed_count, runes_earned, mood_avg, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
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
                day.isoformat(), generated_at.isoformat(), sessions_count, focused_minutes,
                completion_rate, len(completed_today), runes_earned, mood_avg,
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


def _row_to_evaluation(row: sqlite3.Row) -> DailyEvaluation:
    day = date_cls.fromisoformat(row["date"])
    summary = json.loads(row["summary_json"])
    return DailyEvaluation(
        date=day, generated_at=datetime.fromisoformat(row["generated_at"]),
        sessions_count=row["sessions_count"], focused_minutes=row["focused_minutes"],
        completion_rate=row["completion_rate"], tasks_completed_count=row["tasks_completed_count"],
        runes_earned=row["runes_earned"], mood_avg=row["mood_avg"],
        mood_entries=list_mood_entries(day),
        tasks_completed_names=summary.get("tasks_completed_names", []),
        quadrant_breakdown=summary.get("quadrant_breakdown", {}),
    )


def get_evaluation(day: date_cls) -> Optional[DailyEvaluation]:
    """The persisted snapshot for `day`, if one has been generated."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM daily_evaluations WHERE date = ?", (day.isoformat(),)
        ).fetchone()
    return _row_to_evaluation(row) if row else None


def list_evaluations(days: int = 7) -> List[DailyEvaluation]:
    """The most recent `days` persisted snapshots, most recent first --
    used for the frontend's short mood/focus trend view. Only returns
    dates that actually have a generated evaluation (no gap-filling)."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM daily_evaluations ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
    return [_row_to_evaluation(r) for r in rows]


def has_logged_today(day: Optional[date_cls] = None) -> bool:
    """True if `day` (default today) already has a mood entry or a
    generated evaluation snapshot -- the sole signal the end-of-day
    reminder banner uses to decide whether to show itself."""
    day = day or date_cls.today()
    return bool(list_mood_entries(day)) or get_evaluation(day) is not None
