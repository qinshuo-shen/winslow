"""
Project tracking (2026-08 page-split redesign) -- a standalone entity for
work that naturally spans more than one task. Deliberately NOT built on top
of tasks.py's existing tag Project/sub-project hierarchy (that stays exactly
as-is, a generic label system) -- a Project here is a real trackable object
with its own status/notes lifecycle and a set of member tasks, tagged the
same way a task is tagged (via the same shared `tags` table, through a new
`project_tags` join mirroring `task_tags`).

No manual ordering column: the roadmap timeline this module backs
(tasks.list_tasks_for_project) orders by creation order. The Board itself
turned out to still be button-based despite `@dnd-kit/core` being a listed
dependency, so a reorder feature isn't being introduced here either -- see
tasks.py's `position` column, which the frontend never actually writes.

Multi-user follow-up: `projects` gained a `user_id` column (simple additive
ALTER TABLE -- no uniqueness constraint involves it, unlike tasks.py's
`tags` table). `project_tags` needs no `user_id` of its own, same reasoning
as `task_tags`: it's a pure join table keyed by `project_id`, already
user-scoped.
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .config import SESSION_DB_PATH
from .tasks import ALL_STATUSES, STATUS_NOT_STARTED, _get_or_create_tag_id, _normalize_tags
from .tasks import _connect as _ensure_tags_table

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_tags (
    project_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (project_id, tag_id)
);
"""

# Nullable for the same reason tasks.py's own _NEW_COLUMNS entry is:
# ALTER TABLE can't add a NOT NULL column with no default to a table that
# already has rows. scripts/bootstrap_multiuser.py backfills existing NULL
# rows to the owner's account.
_NEW_COLUMNS = {"user_id": "INTEGER"}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    for name, coltype in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {name} {coltype}")


def _connect() -> sqlite3.Connection:
    # project_tags references the shared `tags` table, which tasks.py owns
    # and creates lazily on its own first connection -- ensure that's
    # already run before this module's own schema, rather than duplicating
    # the CREATE TABLE here (this module never had a `tags` table until
    # this line, running against a fresh DB before any task had ever been
    # created hit exactly this gap).
    _ensure_tags_table().close()
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn


@dataclass
class Project:
    id: int
    user_id: int
    name: str
    status: str
    notes: str
    created_at: datetime
    tags: List[str] = field(default_factory=list)


def _row_to_project(row: sqlite3.Row, tags: Optional[List[str]] = None) -> Project:
    return Project(
        id=row["id"], user_id=row["user_id"], name=row["name"], status=row["status"],
        notes=row["notes"], created_at=datetime.fromisoformat(row["created_at"]),
        tags=tags or [],
    )


def _tags_by_project_id(conn: sqlite3.Connection, project_ids: List[int]) -> dict:
    result = {pid: [] for pid in project_ids}
    if not project_ids:
        return result
    placeholders = ",".join("?" * len(project_ids))
    rows = conn.execute(
        f"SELECT project_tags.project_id, tags.name FROM project_tags "
        f"JOIN tags ON tags.id = project_tags.tag_id "
        f"WHERE project_tags.project_id IN ({placeholders}) ORDER BY tags.name COLLATE NOCASE",
        project_ids,
    ).fetchall()
    for project_id, tag_name in rows:
        result[project_id].append(tag_name)
    return result


def _set_project_tags_locked(
    conn: sqlite3.Connection, user_id: int, project_id: int, tag_names: List[str]
) -> None:
    """Same shape as tasks._set_task_tags_locked -- replaces the project's
    full tag set, creating any tag that doesn't already exist. Must be
    called with `conn` already open; does not commit. Caller is
    responsible for having already verified `project_id` belongs to
    `user_id`."""
    names = _normalize_tags(tag_names)
    conn.execute("DELETE FROM project_tags WHERE project_id = ?", (project_id,))
    for name in names:
        tag_id = _get_or_create_tag_id(conn, user_id, name)
        conn.execute(
            "INSERT OR IGNORE INTO project_tags (project_id, tag_id) VALUES (?, ?)",
            (project_id, tag_id),
        )


def add_project(user_id: int, name: str, notes: str = "", tags: Optional[List[str]] = None) -> Project:
    name = name.strip()
    if not name:
        raise ValueError("Project name can't be empty")
    created_at = datetime.now()
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO projects (user_id, name, status, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, STATUS_NOT_STARTED, notes, created_at.isoformat()),
        )
        project_id = cur.lastrowid
        normalized_tags = _normalize_tags(tags) if tags else []
        if normalized_tags:
            _set_project_tags_locked(conn, user_id, project_id, normalized_tags)
        conn.commit()
    return Project(
        id=project_id, user_id=user_id, name=name, status=STATUS_NOT_STARTED, notes=notes,
        created_at=created_at, tags=normalized_tags,
    )


def list_projects(user_id: int) -> List[Project]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at", (user_id,)
        ).fetchall()
        tags_by_id = _tags_by_project_id(conn, [r["id"] for r in rows])
    return [_row_to_project(r, tags_by_id[r["id"]]) for r in rows]


def get_project(user_id: int, project_id: int) -> Optional[Project]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
        ).fetchone()
        if row is None:
            return None
        tags_by_id = _tags_by_project_id(conn, [project_id])
    return _row_to_project(row, tags_by_id[project_id])


def update_project(
    user_id: int,
    project_id: int,
    name: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Optional[Project]:
    """Partial update -- only fields explicitly passed (non-None) are
    changed, same convention as tasks.update_task. Returns None for a
    `project_id` that doesn't exist or isn't owned by `user_id`, checked up
    front for the same reason tasks.update_task checks it: `project_tags`
    has no `user_id` of its own, so a `tags` edit isn't itself gated by the
    WHERE-scoped UPDATE below."""
    if get_project(user_id, project_id) is None:
        return None
    if status is not None and status not in ALL_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")

    fields = []
    values: list = []
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("Project name can't be empty")
        fields.append("name = ?")
        values.append(name)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes)

    if not fields and tags is None:
        return get_project(user_id, project_id)

    with closing(_connect()) as conn:
        if fields:
            conn.execute(
                f"UPDATE projects SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                values + [project_id, user_id],
            )
        if tags is not None:
            _set_project_tags_locked(conn, user_id, project_id, tags)
        conn.commit()
    return get_project(user_id, project_id)


def delete_project(user_id: int, project_id: int) -> None:
    """Disconnects member tasks (project_id -> NULL) rather than deleting
    them -- same "don't cascade-delete real user data" instinct as
    tasks.delete_task() clearing task_tags before dropping the task row.
    No-op for a `project_id` that doesn't exist or isn't owned by
    `user_id` -- checked up front, same reasoning as update_project above."""
    if get_project(user_id, project_id) is None:
        return
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE tasks SET project_id = NULL WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        )
        conn.execute("DELETE FROM project_tags WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
        conn.commit()
