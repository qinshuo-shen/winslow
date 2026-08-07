"""
Questlines (RPG reward system, Phase F -- see character.py's docstring for
the overall design). A light progress counter, not full quest content:
Notion's "Specific Project" multi_select tag (previously parsed but unused
-- see notion_tasks.Task.specific_project) groups completed focus sessions
into a per-project counter, paying a flat Rune bonus every
QUESTLINE_MILESTONE_SESSIONS-th completed session under the same project.
"""
import sqlite3
from contextlib import closing
from typing import Optional

from .config import QUESTLINE_MILESTONE_BONUS_RUNES, QUESTLINE_MILESTONE_SESSIONS, SESSION_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questline_progress (
    project_name TEXT PRIMARY KEY,
    session_count INTEGER NOT NULL DEFAULT 0,
    milestones_paid INTEGER NOT NULL DEFAULT 0
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def record_questline_progress(project_name: str) -> Optional[str]:
    """
    Called after a completed session tagged with `project_name`. Increments
    that project's session counter and, if it just crossed a
    QUESTLINE_MILESTONE_SESSIONS-th milestone, awards a flat Rune bonus and
    returns a note describing it. Returns None if no milestone was hit.
    """
    from . import character

    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO questline_progress (project_name, session_count, milestones_paid) "
            "VALUES (?, 1, 0) "
            "ON CONFLICT(project_name) DO UPDATE SET session_count = session_count + 1",
            (project_name,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT session_count, milestones_paid FROM questline_progress WHERE project_name = ?",
            (project_name,),
        ).fetchone()
        session_count, milestones_paid = row

        earned_milestones = session_count // QUESTLINE_MILESTONE_SESSIONS
        if earned_milestones <= milestones_paid:
            return None

        conn.execute(
            "UPDATE questline_progress SET milestones_paid = ? WHERE project_name = ?",
            (earned_milestones, project_name),
        )
        conn.commit()

    character.award_runes(QUESTLINE_MILESTONE_BONUS_RUNES)
    return (f"questline milestone! {session_count} sessions on {project_name!r} -- "
            f"+{QUESTLINE_MILESTONE_BONUS_RUNES} bonus Runes")


def get_progress(project_name: str) -> int:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT session_count FROM questline_progress WHERE project_name = ?", (project_name,)
        ).fetchone()
    return row[0] if row else 0


def list_active_questlines():
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT project_name, session_count, milestones_paid FROM questline_progress "
            "ORDER BY session_count DESC"
        ).fetchall()
