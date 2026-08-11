"""
Native task tracker (2026-08-11 redesign) -- replaces notion_tasks.py as the
app's task backlog. Tasks are created and tracked directly in-app instead of
synced from an external Notion database; each is assigned by the user to
one quadrant of the same Impact/Effort priority matrix notion_tasks.py used
(the exact strings are reused, not renamed, so focus_timer.py's existing
Rune-multiplier/duration tables -- which key off these strings -- keep
working unchanged).

notion_tasks.py is left on disk, untouched and no longer called by the
default app flow -- see procrastination_tool/migrate_notion_tasks.py for
the one-time extraction that replaces it.

2026-08-11, same-day follow-up: the original push-based "Now" nudge surface
this module was first built for was retired in favor of a browsable,
Notion-style two-column Board (Today / Task Pool, grouped by quadrant --
see the attached screenshot in the redesign plan). Added `specific_project`
(carried over from Notion, used for grouping/tagging), `is_today` (which
column a task is in -- manually set by the user, mirroring how Notion's
"Today" view was just a manually-curated filter, not automatic),
`position` (manual order within a column+quadrant), `completed_at` (needed
by the end-of-day evaluation's "tasks completed today" count), and an
`on_hold` status matching Notion's status set (minus "Discarded", which
becomes a delete here).

2026-08-11, second same-day follow-up: free-form multi-value tags (distinct
from `specific_project`, which stays a single string -- character.py/
questlines.py already key off a session's one `specific_project` string for
RPG milestone tracking, so that field's shape can't change). Mirrors
Notion's 'Block' (single-select life-area) and 'Specific Project'
(multi-select) properties, both of which read as "tags" to the user --
migrate_notion_tasks.py folds both into one tag list per task. `tags` and
`task_tags` are a normal two-table tag model (not a comma-joined column) so
"create a new tag" and "what tags already exist" (for autocomplete) are
trivial queries, and a typo'd tag doesn't silently fork into a near-
duplicate the way ad hoc string splitting would encourage.
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .config import SESSION_DB_PATH
from .notion_tasks import PRIORITY_DURATION_MINUTES, PRIORITY_ORDER

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_ON_HOLD = "on_hold"
STATUS_COMPLETED = "completed"
ALL_STATUSES = (STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_ON_HOLD, STATUS_COMPLETED)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    priority TEXT NOT NULL,
    effort_minutes INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'not_started',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS task_tags (
    task_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (task_id, tag_id)
);
"""

# Guarded ALTER TABLE additions -- same lazy-migration pattern used by
# deadlines.py/proactive_scheduler.py, safe to run against a DB that
# already has these columns (see _ensure_columns).
_NEW_COLUMNS = {
    "specific_project": "TEXT",
    "is_today": "INTEGER NOT NULL DEFAULT 0",
    "position": "INTEGER NOT NULL DEFAULT 0",
    "completed_at": "TEXT",
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    for name, coltype in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {coltype}")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn


@dataclass
class Task:
    id: int
    name: str
    priority: str
    effort_minutes: int
    notes: str
    status: str
    created_at: datetime
    specific_project: Optional[str]
    is_today: bool
    position: int
    completed_at: Optional[datetime]
    tags: List[str] = field(default_factory=list)


def _row_to_task(row: sqlite3.Row, tags: Optional[List[str]] = None) -> Task:
    return Task(
        id=row["id"], name=row["name"], priority=row["priority"],
        effort_minutes=row["effort_minutes"], notes=row["notes"],
        status=row["status"], created_at=datetime.fromisoformat(row["created_at"]),
        specific_project=row["specific_project"],
        is_today=bool(row["is_today"]),
        position=row["position"],
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        tags=tags or [],
    )


def _tags_by_task_id(conn: sqlite3.Connection, task_ids: List[int]) -> Dict[int, List[str]]:
    result: Dict[int, List[str]] = {tid: [] for tid in task_ids}
    if not task_ids:
        return result
    placeholders = ",".join("?" * len(task_ids))
    rows = conn.execute(
        f"SELECT task_tags.task_id, tags.name FROM task_tags "
        f"JOIN tags ON tags.id = task_tags.tag_id "
        f"WHERE task_tags.task_id IN ({placeholders}) ORDER BY tags.name COLLATE NOCASE",
        task_ids,
    ).fetchall()
    for task_id, tag_name in rows:
        result[task_id].append(tag_name)
    return result


def _normalize_tags(tag_names: List[str]) -> List[str]:
    seen = set()
    result = []
    for raw in tag_names:
        name = raw.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        result.append(name)
    return result


def _set_task_tags_locked(conn: sqlite3.Connection, task_id: int, tag_names: List[str]) -> None:
    """Replace `task_id`'s full tag set with `tag_names`, creating any tag
    that doesn't already exist yet (case-sensitive match -- "PQi" and "pqi"
    are treated as distinct tags, same as Notion select options). Must be
    called with `conn` already open; does not commit (caller's
    responsibility, same convention as the rest of this module's
    multi-statement writes)."""
    names = _normalize_tags(tag_names)
    conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    for name in names:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)", (task_id, tag_id)
        )


def list_tags() -> List[str]:
    """Every tag that's ever been created, alphabetically -- the
    autocomplete source for the Board's tag editor. Persists independently
    of current usage (same as a Notion select property's option list), so
    a tag remains pickable even if the last task wearing it is deleted."""
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT name FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    return [r[0] for r in rows]


def add_task(
    name: str,
    priority: str,
    notes: str = "",
    specific_project: Optional[str] = None,
    status: str = STATUS_NOT_STARTED,
    tags: Optional[List[str]] = None,
) -> Task:
    """`status` defaults to not-started for normal in-app task creation, but
    is accepted as a parameter so migrate_notion_tasks.py can preserve each
    Notion task's actual status (in-progress/on-hold/completed) instead of
    resetting everything to not-started on import."""
    name = name.strip()
    if not name:
        raise ValueError("Task name can't be empty")
    if priority not in PRIORITY_ORDER:
        raise ValueError(f"Unknown priority quadrant: {priority!r}")
    if status not in ALL_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")
    effort_minutes = PRIORITY_DURATION_MINUTES.get(priority, 60)
    created_at = datetime.now()
    completed_at = created_at if status == STATUS_COMPLETED else None
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO tasks (name, priority, effort_minutes, notes, status, created_at, "
            "specific_project, is_today, position, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)",
            (name, priority, effort_minutes, notes, status, created_at.isoformat(),
             specific_project, completed_at.isoformat() if completed_at else None),
        )
        task_id = cur.lastrowid
        normalized_tags = _normalize_tags(tags) if tags else []
        if normalized_tags:
            _set_task_tags_locked(conn, task_id, normalized_tags)
        conn.commit()
    return Task(
        id=task_id, name=name, priority=priority, effort_minutes=effort_minutes,
        notes=notes, status=status, created_at=created_at,
        specific_project=specific_project, is_today=False, position=0,
        completed_at=completed_at, tags=normalized_tags,
    )


def list_actionable_tasks() -> List[Task]:
    """Not-started/in-progress tasks, ranked effort-first (same PRIORITY_ORDER
    notion_tasks.py used), tie-broken by creation order. There's no start-date
    filtering here -- native tasks have no start-date concept, they're
    actionable from the moment they're created."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status IN (?, ?) ORDER BY id",
            (STATUS_NOT_STARTED, STATUS_IN_PROGRESS),
        ).fetchall()
        tags_by_id = _tags_by_task_id(conn, [r["id"] for r in rows])
    result = [_row_to_task(r, tags_by_id[r["id"]]) for r in rows]

    def sort_key(t: Task):
        rank = PRIORITY_ORDER.index(t.priority) if t.priority in PRIORITY_ORDER else len(PRIORITY_ORDER)
        return (rank, t.created_at)

    result.sort(key=sort_key)
    return result


def list_all_tasks() -> List[Task]:
    """Every task regardless of status -- the Board's data source (unlike
    list_actionable_tasks(), which deliberately excludes on-hold/completed
    since it's meant for the old proactive-nudge picker). Ordered by
    quadrant rank, then manual `position`, then creation order."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM tasks").fetchall()
        tags_by_id = _tags_by_task_id(conn, [r["id"] for r in rows])
    result = [_row_to_task(r, tags_by_id[r["id"]]) for r in rows]

    def sort_key(t: Task):
        rank = PRIORITY_ORDER.index(t.priority) if t.priority in PRIORITY_ORDER else len(PRIORITY_ORDER)
        return (rank, t.position, t.created_at)

    result.sort(key=sort_key)
    return result


def get_task(task_id: int) -> Optional[Task]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        tags_by_id = _tags_by_task_id(conn, [task_id])
    return _row_to_task(row, tags_by_id[task_id])


def update_task(
    task_id: int,
    name: Optional[str] = None,
    priority: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    specific_project: Optional[str] = None,
    is_today: Optional[bool] = None,
    position: Optional[int] = None,
    tags: Optional[List[str]] = None,
) -> Optional[Task]:
    """Generic partial update for the Board (status/quadrant/today-toggle/
    reorder/notes/tags edits) -- only fields explicitly passed (non-None)
    are changed. `specific_project` can't be cleared this way (a None here
    means "leave unchanged", same as every other field) -- pass "" to clear
    it. `tags`, if passed, REPLACES the task's full tag set (not a merge) --
    the frontend always sends the complete desired list, same as how a
    Notion multi-select field is edited."""
    if priority is not None and priority not in PRIORITY_ORDER:
        raise ValueError(f"Unknown priority quadrant: {priority!r}")
    if status is not None and status not in ALL_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")

    fields = []
    values: list = []
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("Task name can't be empty")
        fields.append("name = ?")
        values.append(name)
    if priority is not None:
        fields.append("priority = ?")
        values.append(priority)
        fields.append("effort_minutes = ?")
        values.append(PRIORITY_DURATION_MINUTES.get(priority, 60))
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
        fields.append("completed_at = ?")
        values.append(datetime.now().isoformat() if status == STATUS_COMPLETED else None)
    if specific_project is not None:
        fields.append("specific_project = ?")
        values.append(specific_project if specific_project != "" else None)
    if is_today is not None:
        fields.append("is_today = ?")
        values.append(1 if is_today else 0)
    if position is not None:
        fields.append("position = ?")
        values.append(position)

    if not fields and tags is None:
        return get_task(task_id)

    with closing(_connect()) as conn:
        if fields:
            values_with_id = values + [task_id]
            conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values_with_id)
        if tags is not None:
            _set_task_tags_locked(conn, task_id, tags)
        conn.commit()
    return get_task(task_id)


def mark_in_progress(task_id: int) -> None:
    update_task(task_id, status=STATUS_IN_PROGRESS)


def mark_completed(task_id: int) -> None:
    update_task(task_id, status=STATUS_COMPLETED)


def delete_task(task_id: int) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
