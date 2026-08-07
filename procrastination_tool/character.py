"""
RPG reward system (2026-08-06 redesign, replaces the spin wheel --
see spin_wheel.py's docstring for why the original wheel wasn't kept as the
live reward path). Soulslike-themed: a single "Runes" currency, earned by
completing focus sessions and spent on deliberate ("bonfire") stat leveling
via the `focus rest` CLI command -- leveling never happens automatically on
earning Runes, only on that explicit action.

Character level shown to the user is the sum of the four stat levels (a
simple, legible aggregate -- there's no separate "character level" counter
tracked independently of the stats themselves).

All state lives in the existing data/sessions.db, via this project's
established guarded CREATE TABLE IF NOT EXISTS + ALTER TABLE lazy-migration
pattern (see focus_timer.py).
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from .config import (
    BASE_RUNES_PER_MINUTE,
    CHARACTER_STATS,
    DEFAULT_RUNE_MULTIPLIER,
    PRIORITY_RUNE_MULTIPLIER,
    SESSION_DB_PATH,
    stat_level_cost,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS character (
    id INTEGER PRIMARY KEY,
    runes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS character_stats (
    stat_name TEXT PRIMARY KEY,
    level INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS level_up_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    stat_name TEXT NOT NULL,
    new_level INTEGER NOT NULL,
    runes_spent INTEGER NOT NULL
);
"""

_CHARACTER_ROW_ID = 1


@dataclass
class Character:
    runes: int
    stats: Dict[str, int]

    @property
    def level(self) -> int:
        return sum(self.stats.values())


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO character (id, runes) VALUES (?, 0)", (_CHARACTER_ROW_ID,)
    )
    for stat_name in CHARACTER_STATS:
        conn.execute(
            "INSERT OR IGNORE INTO character_stats (stat_name, level) VALUES (?, 0)",
            (stat_name,),
        )
    conn.commit()
    return conn


def calculate_rune_award(priority: Optional[str], actual_minutes: float) -> int:
    multiplier = PRIORITY_RUNE_MULTIPLIER.get(priority, DEFAULT_RUNE_MULTIPLIER)
    return round(actual_minutes * multiplier * BASE_RUNES_PER_MINUTE)


def get_character() -> Character:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        runes = conn.execute(
            "SELECT runes FROM character WHERE id = ?", (_CHARACTER_ROW_ID,)
        ).fetchone()["runes"]
        stat_rows = conn.execute("SELECT stat_name, level FROM character_stats").fetchall()
    return Character(runes=runes, stats={r["stat_name"]: r["level"] for r in stat_rows})


def award_runes(amount: int) -> int:
    """Add `amount` Runes to the balance. Returns the new balance."""
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE character SET runes = runes + ? WHERE id = ?", (amount, _CHARACTER_ROW_ID)
        )
        conn.commit()
        return conn.execute(
            "SELECT runes FROM character WHERE id = ?", (_CHARACTER_ROW_ID,)
        ).fetchone()[0]


def spend_runes_on_stat(stat_name: str) -> "tuple[int, int]":
    """
    Bonfire leveling: spend Runes to raise `stat_name` by one level. Returns
    (new_level, runes_spent). Raises ValueError if the stat name is unknown
    or the Rune balance can't cover the cost.
    """
    if stat_name not in CHARACTER_STATS:
        raise ValueError(f"Unknown stat {stat_name!r} -- must be one of {CHARACTER_STATS}")

    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT runes FROM character WHERE id = ?", (_CHARACTER_ROW_ID,)
        ).fetchone()
        balance = row[0]
        current_level = conn.execute(
            "SELECT level FROM character_stats WHERE stat_name = ?", (stat_name,)
        ).fetchone()[0]
        cost = stat_level_cost(current_level)
        if balance < cost:
            raise ValueError(
                f"Not enough Runes to level {stat_name} (need {cost}, have {balance})"
            )

        new_level = current_level + 1
        conn.execute("UPDATE character SET runes = runes - ? WHERE id = ?", (cost, _CHARACTER_ROW_ID))
        conn.execute(
            "UPDATE character_stats SET level = ? WHERE stat_name = ?", (new_level, stat_name)
        )
        conn.execute(
            "INSERT INTO level_up_log (ts, stat_name, new_level, runes_spent) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), stat_name, new_level, cost),
        )
        conn.commit()
        return new_level, cost
