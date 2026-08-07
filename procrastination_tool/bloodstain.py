"""
Bloodstain death/recovery (RPG reward system, Phase B -- see character.py's
docstring for the overall design). Souls games drop your currency at the
death spot when you die, recoverable if you return before dying again. Here:
a `failed_pause_timeout` session's Runes aren't simply lost, they sit in a
bloodstain for a BLOODSTAIN_EXPIRY_HOURS window, recovered automatically by
the next completed session. Only one bloodstain is ever live at a time --
a new failure while one is still active replaces it (matches Souls behavior:
dying again erases the previous bloodstain).

This is deliberately gentler than either "no penalty" (weakens the incentive
to actually finish) or "total loss" (risks compounding the shame spiral that
often *causes* procrastination) -- it rewards specifically the behavior the
tool wants to reinforce: getting back up soon after a slip.
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .config import BLOODSTAIN_EXPIRY_HOURS, SESSION_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bloodstains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    runes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    session_id INTEGER,
    recovered INTEGER NOT NULL DEFAULT 0
)
"""


@dataclass
class Bloodstain:
    id: int
    runes: int
    created_at: datetime
    session_id: Optional[int]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def create_bloodstain(runes: int, session_id: Optional[int] = None) -> None:
    """Park `runes` in a new bloodstain. Only one is ever live -- any
    existing unrecovered bloodstain is marked recovered=0 replaced (Souls
    behavior: dying again erases the previous bloodstain, it isn't stacked)."""
    with closing(_connect()) as conn:
        conn.execute("UPDATE bloodstains SET recovered = 1 WHERE recovered = 0")
        conn.execute(
            "INSERT INTO bloodstains (runes, created_at, session_id, recovered) VALUES (?, ?, ?, 0)",
            (runes, datetime.now().isoformat(), session_id),
        )
        conn.commit()


def get_active_bloodstain() -> Optional[Bloodstain]:
    """Returns the live, unexpired, unrecovered bloodstain, if any."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM bloodstains WHERE recovered = 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    created_at = datetime.fromisoformat(row["created_at"])
    if datetime.now() - created_at > timedelta(hours=BLOODSTAIN_EXPIRY_HOURS):
        return None
    return Bloodstain(id=row["id"], runes=row["runes"], created_at=created_at, session_id=row["session_id"])


def recover_active_bloodstain() -> Optional[int]:
    """
    Called after a completed session. If an active (unexpired, unrecovered)
    bloodstain exists, marks it recovered and returns its Rune amount so the
    caller can award it. Returns None if there's nothing to recover.
    """
    stain = get_active_bloodstain()
    if stain is None:
        return None
    with closing(_connect()) as conn:
        conn.execute("UPDATE bloodstains SET recovered = 1 WHERE id = ?", (stain.id,))
        conn.commit()
    return stain.runes
