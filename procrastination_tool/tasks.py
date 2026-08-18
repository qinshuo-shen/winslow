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

2026-08-11, fourth same-day follow-up: tags gained a two-level hierarchy --
`parent_id` (nullable, self-referencing) turns a tag into either a
top-level "Project" (parent_id IS NULL -- e.g. "PhD core", "Education") or
a sub-project nested under one (e.g. "Paper 2" under "PhD core"). Enforced
to exactly two levels: set_tag_parent() rejects parenting a tag under
another tag that itself has a parent, so chains can't go deeper -- the
user asked for "a few project level (highest) tabs, then sub-project level
tabs," not arbitrary nesting. See reclassify_tags.py for the real
categorization applied to this project's actual tags (PhD core/PhD side/
Education/ASPARi operation/Personal), confirmed with the user rather than
guessed.

Multi-user follow-up: every function now takes a leading `user_id` and
scopes its query by it. `tags.name UNIQUE` became `UNIQUE(user_id, name)`
(one user's tag name shouldn't block another's) and `today_rollover`/
`week_rollover` -- previously true singleton rows (`CHECK (id = 1)`) --
became one row per user (`user_id INTEGER PRIMARY KEY`). Both are schema
changes ALTER TABLE can't make in place on an existing DB; the one-time
scripts/bootstrap_multiuser.py rebuilds them for the real, already-populated
data/sessions.db. `task_tags` needs no `user_id` of its own -- it's a pure
join table keyed by `task_id`, which is already user-scoped.
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime
from typing import Dict, List, Optional

from .config import SESSION_DB_PATH
from .notion_tasks import PRIORITY_DURATION_MINUTES, PRIORITY_ORDER
from .weekly import week_start_date

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_ON_HOLD = "on_hold"
STATUS_COMPLETED = "completed"
ALL_STATUSES = (STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_ON_HOLD, STATUS_COMPLETED)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    priority TEXT NOT NULL,
    effort_minutes INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'not_started',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(user_id, name)
);
CREATE TABLE IF NOT EXISTS task_tags (
    task_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (task_id, tag_id)
);
CREATE TABLE IF NOT EXISTS today_rollover (
    user_id INTEGER PRIMARY KEY,
    last_run_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS week_rollover (
    user_id INTEGER PRIMARY KEY,
    last_run_week_start TEXT NOT NULL
);
"""

# Guarded ALTER TABLE additions -- same lazy-migration pattern used by
# deadlines.py/proactive_scheduler.py, safe to run against a DB that
# already has these columns (see _ensure_columns). `user_id` is nullable
# here (SQLite can't add a NOT NULL column with no default to a table that
# already has rows) -- scripts/bootstrap_multiuser.py backfills any
# pre-existing NULL rows to the owner's account; every new row from
# add_task() always supplies a real one.
_NEW_COLUMNS = {
    "user_id": "INTEGER",
    "specific_project": "TEXT",
    "is_today": "INTEGER NOT NULL DEFAULT 0",
    "position": "INTEGER NOT NULL DEFAULT 0",
    "completed_at": "TEXT",
    # Set only on the single task chosen by a given day's roll_over_today()
    # run; compared against "today" at the API layer (BacklogTaskOut's
    # carried_forward field) so yesterday's marker goes stale for free,
    # with no extra write needed to clear it.
    "carried_forward_date": "TEXT",
    # Sprint/weekly commitment (Scrum-lite feature set): mirrors is_today's
    # shape at a coarser granularity. is_this_week is a manual toggle;
    # week_committed_date is set to that week's Monday only when
    # is_this_week flips False->True, and is deliberately left untouched
    # when it flips back off -- same "historical marker that goes stale for
    # free" reasoning as carried_forward_date, used by the weekly retro to
    # compute committed-vs-completed after roll_over_week() has cleared
    # is_this_week for the week.
    "is_this_week": "INTEGER NOT NULL DEFAULT 0",
    "week_committed_date": "TEXT",
    # 2026-08 page-split redesign: optional link to a projects.py Project
    # this task is a breakdown step of -- see that module's docstring for
    # why it's a new standalone table rather than reusing the tag Project
    # hierarchy below. Unenforced at the SQLite level (this project never
    # turns PRAGMA foreign_keys on) -- cleared explicitly by
    # projects.delete_project() rather than relying on a real FK cascade.
    "project_id": "INTEGER REFERENCES projects(id)",
    # Draft-stage breakdown steps: a Roadmap quick-add step can opt into
    # starting as a draft (checkbox at add time) instead of landing
    # straight in the Task Pool -- same manual-boolean-gate shape as
    # is_today/is_this_week above, kept independent of `status` since
    # "not yet released to the pool" is an unrelated axis from
    # not-started/in-progress/on-hold/completed. DEFAULT 0 so existing
    # rows and any caller that omits it keep today's "instantly in the
    # pool" behavior.
    "is_draft": "INTEGER NOT NULL DEFAULT 0",
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    for name, coltype in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {coltype}")

    tag_columns = {row[1] for row in conn.execute("PRAGMA table_info(tags)")}
    if "parent_id" not in tag_columns:
        conn.execute("ALTER TABLE tags ADD COLUMN parent_id INTEGER REFERENCES tags(id)")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn


@dataclass
class Task:
    id: int
    user_id: int
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
    carried_forward_date: Optional[str] = None
    is_this_week: bool = False
    week_committed_date: Optional[str] = None
    project_id: Optional[int] = None
    is_draft: bool = False


def _row_to_task(row: sqlite3.Row, tags: Optional[List[str]] = None) -> Task:
    return Task(
        id=row["id"], user_id=row["user_id"], name=row["name"], priority=row["priority"],
        effort_minutes=row["effort_minutes"], notes=row["notes"],
        status=row["status"], created_at=datetime.fromisoformat(row["created_at"]),
        specific_project=row["specific_project"],
        is_today=bool(row["is_today"]),
        position=row["position"],
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        tags=tags or [],
        carried_forward_date=row["carried_forward_date"],
        is_this_week=bool(row["is_this_week"]),
        week_committed_date=row["week_committed_date"],
        project_id=row["project_id"],
        is_draft=bool(row["is_draft"]),
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


def _set_task_tags_locked(
    conn: sqlite3.Connection, user_id: int, task_id: int, tag_names: List[str]
) -> None:
    """Replace `task_id`'s full tag set with `tag_names`, creating any tag
    that doesn't already exist yet (case-sensitive match -- "PQi" and "pqi"
    are treated as distinct tags, same as Notion select options). Must be
    called with `conn` already open; does not commit (caller's
    responsibility, same convention as the rest of this module's
    multi-statement writes). Caller is responsible for having already
    verified `task_id` belongs to `user_id` -- this function trusts it."""
    names = _normalize_tags(tag_names)
    conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    for name in names:
        tag_id = _get_or_create_tag_id(conn, user_id, name)
        conn.execute(
            "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)", (task_id, tag_id)
        )


@dataclass
class TagInfo:
    name: str
    parent: Optional[str]  # None for a top-level "Project" tag


def list_tags(user_id: int) -> List[TagInfo]:
    """Every tag `user_id` has ever created, alphabetically, with its parent
    (if any) -- the source for the Board's project tabs and the tag
    editor's project/sub-tag picker. Persists independently of current
    usage (same as a Notion select property's option list), so a tag
    remains pickable even if the last task wearing it is deleted."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT t.name, p.name FROM tags t LEFT JOIN tags p ON p.id = t.parent_id "
            "WHERE t.user_id = ? ORDER BY t.name COLLATE NOCASE",
            (user_id,),
        ).fetchall()
    return [TagInfo(name=r[0], parent=r[1]) for r in rows]


def _get_or_create_tag_id(conn: sqlite3.Connection, user_id: int, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO tags (user_id, name) VALUES (?, ?)", (user_id, name))
    return conn.execute(
        "SELECT id FROM tags WHERE user_id = ? AND name = ?", (user_id, name)
    ).fetchone()[0]


def set_tag_parent(user_id: int, name: str, parent: Optional[str]) -> TagInfo:
    """Create `name` (if it doesn't already exist for `user_id`) and set its
    parent to `parent` (creating that too if needed), or clear it back to
    top-level if `parent` is None. Enforces exactly two levels: `parent`
    must itself be a top-level tag (no parent of its own) -- raises
    ValueError for a self-parent or a parent that already has a parent,
    rather than silently allowing a deeper chain than the Board's
    two-tab-row UI can represent."""
    name = name.strip()
    if not name:
        raise ValueError("Tag name can't be empty")
    if parent is not None:
        parent = parent.strip()
        if parent == name:
            raise ValueError("A tag can't be its own parent")

    with closing(_connect()) as conn:
        tag_id = _get_or_create_tag_id(conn, user_id, name)

        if parent is None:
            conn.execute("UPDATE tags SET parent_id = NULL WHERE id = ?", (tag_id,))
        else:
            parent_id = _get_or_create_tag_id(conn, user_id, parent)
            parent_of_parent = conn.execute(
                "SELECT parent_id FROM tags WHERE id = ?", (parent_id,)
            ).fetchone()[0]
            if parent_of_parent is not None:
                raise ValueError(
                    f"{parent!r} is itself a sub-tag -- only a top-level tag can be a parent"
                )
            conn.execute("UPDATE tags SET parent_id = ? WHERE id = ?", (parent_id, tag_id))
        conn.commit()

        row = conn.execute(
            "SELECT t.name, p.name FROM tags t LEFT JOIN tags p ON p.id = t.parent_id WHERE t.id = ?",
            (tag_id,),
        ).fetchone()
    return TagInfo(name=row[0], parent=row[1])


def _check_project_ownership(user_id: int, project_id: Optional[int]) -> None:
    """add_task/update_task's `project_id` link had zero ownership check
    before multi-user -- any task could link to any projects.py Project
    regardless of who owned it. `project_id is None` ("no project"/"leave
    unchanged") and `project_id == 0` (update_task's "unlink" sentinel)
    both mean nothing to check here. Lazy import: projects.py imports names
    from this module at its own top level, so importing it back at this
    module's top level would be circular -- deferring the import to call
    time (after both modules have already finished loading) sidesteps
    that."""
    if project_id is None or project_id == 0:
        return
    from .projects import get_project as _get_project

    if _get_project(user_id, project_id) is None:
        raise ValueError(f"Project {project_id} does not belong to this user")


def add_task(
    user_id: int,
    name: str,
    priority: str,
    notes: str = "",
    specific_project: Optional[str] = None,
    status: str = STATUS_NOT_STARTED,
    tags: Optional[List[str]] = None,
    project_id: Optional[int] = None,
    is_draft: bool = False,
) -> Task:
    """`status` defaults to not-started for normal in-app task creation, but
    is accepted as a parameter so migrate_notion_tasks.py can preserve each
    Notion task's actual status (in-progress/on-hold/completed) instead of
    resetting everything to not-started on import.

    `project_id` optionally links this task as a breakdown step of a
    projects.py Project -- distinct from `specific_project` (legacy
    free-text) and `tags` (the generic label system).

    `is_draft` defaults to False so every existing caller (ad hoc task
    creation, migration) keeps today's "instantly in the Task Pool"
    behavior; only the Roadmap quick-add's opt-in checkbox passes True."""
    name = name.strip()
    if not name:
        raise ValueError("Task name can't be empty")
    if priority not in PRIORITY_ORDER:
        raise ValueError(f"Unknown priority quadrant: {priority!r}")
    if status not in ALL_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")
    _check_project_ownership(user_id, project_id)
    effort_minutes = PRIORITY_DURATION_MINUTES.get(priority, 60)
    created_at = datetime.now()
    completed_at = created_at if status == STATUS_COMPLETED else None
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, name, priority, effort_minutes, notes, status, "
            "created_at, specific_project, is_today, position, completed_at, project_id, "
            "is_draft) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
            (user_id, name, priority, effort_minutes, notes, status, created_at.isoformat(),
             specific_project, completed_at.isoformat() if completed_at else None, project_id,
             1 if is_draft else 0),
        )
        task_id = cur.lastrowid
        normalized_tags = _normalize_tags(tags) if tags else []
        if normalized_tags:
            _set_task_tags_locked(conn, user_id, task_id, normalized_tags)
        conn.commit()
    return Task(
        id=task_id, user_id=user_id, name=name, priority=priority, effort_minutes=effort_minutes,
        notes=notes, status=status, created_at=created_at,
        specific_project=specific_project, is_today=False, position=0,
        completed_at=completed_at, tags=normalized_tags, project_id=project_id,
        is_draft=is_draft,
    )


def list_actionable_tasks(user_id: int) -> List[Task]:
    """Not-started/in-progress tasks, ranked effort-first (same PRIORITY_ORDER
    notion_tasks.py used), tie-broken by creation order. There's no start-date
    filtering here -- native tasks have no start-date concept, they're
    actionable from the moment they're created."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status IN (?, ?) ORDER BY id",
            (user_id, STATUS_NOT_STARTED, STATUS_IN_PROGRESS),
        ).fetchall()
        tags_by_id = _tags_by_task_id(conn, [r["id"] for r in rows])
    result = [_row_to_task(r, tags_by_id[r["id"]]) for r in rows]

    def sort_key(t: Task):
        rank = PRIORITY_ORDER.index(t.priority) if t.priority in PRIORITY_ORDER else len(PRIORITY_ORDER)
        return (rank, t.created_at)

    result.sort(key=sort_key)
    return result


def list_all_tasks(user_id: int) -> List[Task]:
    """Every task `user_id` owns, regardless of status -- the Board's data
    source (unlike list_actionable_tasks(), which deliberately excludes
    on-hold/completed since it's meant for the old proactive-nudge picker).
    Ordered by quadrant rank, then manual `position`, then creation order."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM tasks WHERE user_id = ?", (user_id,)).fetchall()
        tags_by_id = _tags_by_task_id(conn, [r["id"] for r in rows])
    result = [_row_to_task(r, tags_by_id[r["id"]]) for r in rows]

    def sort_key(t: Task):
        rank = PRIORITY_ORDER.index(t.priority) if t.priority in PRIORITY_ORDER else len(PRIORITY_ORDER)
        return (rank, t.position, t.created_at)

    result.sort(key=sort_key)
    return result


def list_tasks_for_project(user_id: int, project_id: int) -> List[Task]:
    """A project's breakdown steps, oldest first -- backs the Project
    roadmap's vertical milestone timeline (see projects.py). Chronological
    order rather than manual `position`, matching list_all_tasks()'s own
    observation that the Board has no real drag-and-drop reordering to
    borrow a "manual order" convention from."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND project_id = ? ORDER BY created_at",
            (user_id, project_id),
        ).fetchall()
        tags_by_id = _tags_by_task_id(conn, [r["id"] for r in rows])
    return [_row_to_task(r, tags_by_id[r["id"]]) for r in rows]


def get_task(user_id: int, task_id: int) -> Optional[Task]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        ).fetchone()
        if row is None:
            return None
        tags_by_id = _tags_by_task_id(conn, [task_id])
    return _row_to_task(row, tags_by_id[task_id])


def update_task(
    user_id: int,
    task_id: int,
    name: Optional[str] = None,
    priority: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    specific_project: Optional[str] = None,
    is_today: Optional[bool] = None,
    position: Optional[int] = None,
    tags: Optional[List[str]] = None,
    is_this_week: Optional[bool] = None,
    project_id: Optional[int] = None,
    is_draft: Optional[bool] = None,
) -> Optional[Task]:
    """Generic partial update for the Board (status/quadrant/today-toggle/
    reorder/notes/tags edits) -- only fields explicitly passed (non-None)
    are changed. `specific_project` can't be cleared this way (a None here
    means "leave unchanged", same as every other field) -- pass "" to clear
    it. `tags`, if passed, REPLACES the task's full tag set (not a merge) --
    the frontend always sends the complete desired list, same as how a
    Notion multi-select field is edited. `is_this_week`, when it flips
    False->True, also stamps week_committed_date with the current week's
    Monday -- flipping True->False leaves that date alone (see the
    _NEW_COLUMNS comment for why). `project_id` follows the same
    "None means leave unchanged" rule -- pass 0 (never a real task/project
    id) to unlink it, since JSON has no way to distinguish "field omitted"
    from "field sent as null" once it reaches an Optional Python param.
    `is_draft` is the Roadmap draft-stage release toggle -- the Board's
    "Release to Pool" action sends `is_draft=False`.

    Returns None for a `task_id` that doesn't exist OR doesn't belong to
    `user_id` -- checked up front, before any mutation, so a wrong-owner
    `tags` edit (which isn't itself gated by the WHERE-scoped UPDATE below)
    can't slip through and touch another user's task_tags rows."""
    if get_task(user_id, task_id) is None:
        return None
    if priority is not None and priority not in PRIORITY_ORDER:
        raise ValueError(f"Unknown priority quadrant: {priority!r}")
    if status is not None and status not in ALL_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")
    if project_id is not None:
        _check_project_ownership(user_id, project_id)

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
    if is_this_week is not None:
        fields.append("is_this_week = ?")
        values.append(1 if is_this_week else 0)
        if is_this_week:
            fields.append("week_committed_date = ?")
            values.append(week_start_date(date_cls.today()).isoformat())
    if project_id is not None:
        fields.append("project_id = ?")
        values.append(project_id if project_id != 0 else None)
    if is_draft is not None:
        fields.append("is_draft = ?")
        values.append(1 if is_draft else 0)

    if not fields and tags is None:
        return get_task(user_id, task_id)

    with closing(_connect()) as conn:
        if fields:
            values_with_id = values + [task_id, user_id]
            conn.execute(
                f"UPDATE tasks SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                values_with_id,
            )
        if tags is not None:
            _set_task_tags_locked(conn, user_id, task_id, tags)
        conn.commit()
    return get_task(user_id, task_id)


def mark_in_progress(user_id: int, task_id: int) -> None:
    update_task(user_id, task_id, status=STATUS_IN_PROGRESS)


def mark_completed(user_id: int, task_id: int) -> None:
    update_task(user_id, task_id, status=STATUS_COMPLETED)


def delete_task(user_id: int, task_id: int) -> None:
    """No-op for a `task_id` that doesn't exist or isn't owned by
    `user_id` -- checked up front for the same reason update_task checks
    it: `task_tags` has no `user_id` of its own, so deleting by bare
    `task_id` without first confirming ownership could touch another
    user's join-table rows for an id collision that can't actually happen
    (ids are global, not per-user) but is cheap to guard against anyway."""
    if get_task(user_id, task_id) is None:
        return
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        conn.commit()


@dataclass
class RolloverResult:
    ran: bool
    carried_task: Optional[Task]
    unmarked_count: int


def _pick_carry_forward_candidate(stale: List[Task]) -> Optional[Task]:
    """Deterministic choice of which one stale (is_today=True, not
    completed) task carries forward into the new day. Prefers an
    in_progress task ("still in progress") over not_started/on_hold; among
    ties, reuses the Board's own existing ordering (quadrant rank, manual
    position, creation order -- see list_all_tasks()) rather than inventing
    a new one."""
    if not stale:
        return None
    in_progress = [t for t in stale if t.status == STATUS_IN_PROGRESS]
    pool = in_progress or stale

    def key(t: Task):
        rank = PRIORITY_ORDER.index(t.priority) if t.priority in PRIORITY_ORDER else len(PRIORITY_ORDER)
        return (rank, t.position, t.created_at)

    return min(pool, key=key)


def roll_over_today(user_id: int, today: Optional[str] = None) -> RolloverResult:
    """Idempotent per calendar day per user (guarded by
    today_rollover.last_run_date, now one row per user_id rather than a
    single global row): carries exactly one stale is_today task forward
    (tagging it with carried_forward_date=today), unmarks every other stale
    is_today task back to the pool, and clears is_today on any completed
    task still flagged (hygiene -- the Board never renders completed tasks
    anyway, but this keeps is_today meaning "actually in Today" in the DB).
    Called lazily from GET /api/backlog rather than a background tick loop
    -- day-rollover has no time-sensitive side effects the way focus-session
    auto-complete does, so it doesn't need one."""
    today = today or datetime.now().date().isoformat()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT last_run_date FROM today_rollover WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row and row["last_run_date"] == today:
            return RolloverResult(ran=False, carried_task=None, unmarked_count=0)

        stale_rows = conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND is_today = 1 AND status != ?",
            (user_id, STATUS_COMPLETED),
        ).fetchall()
        tags_by_id = _tags_by_task_id(conn, [r["id"] for r in stale_rows])
        stale = [_row_to_task(r, tags_by_id[r["id"]]) for r in stale_rows]
        chosen = _pick_carry_forward_candidate(stale)

        for t in stale:
            if chosen and t.id == chosen.id:
                conn.execute(
                    "UPDATE tasks SET carried_forward_date = ? WHERE id = ?",
                    (today, t.id),
                )
            else:
                conn.execute("UPDATE tasks SET is_today = 0 WHERE id = ?", (t.id,))

        conn.execute(
            "UPDATE tasks SET is_today = 0 WHERE user_id = ? AND is_today = 1 AND status = ?",
            (user_id, STATUS_COMPLETED),
        )
        conn.execute(
            "INSERT INTO today_rollover (user_id, last_run_date) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_run_date = excluded.last_run_date",
            (user_id, today),
        )
        conn.commit()

    unmarked = len(stale) - (1 if chosen else 0)
    return RolloverResult(ran=True, carried_task=chosen, unmarked_count=unmarked)


@dataclass
class WeekRolloverResult:
    ran: bool
    cleared_count: int


def roll_over_week(user_id: int, today: Optional[str] = None) -> WeekRolloverResult:
    """Idempotent per ISO week per user (guarded by
    week_rollover.last_run_week_start, now one row per user_id): clears
    is_this_week on every non-completed task still flagged for the week
    that just ended. Deliberately a reset, not an auto-carry like
    roll_over_today() -- re-committing for the new week each Monday is the
    actual "sprint planning" moment this feature exists to create, and
    there's no clean single-task heuristic to generalize the daily
    auto-carry to a weekly, potentially-multi-task set. week_committed_date
    is left untouched on cleared tasks -- it's the historical record the
    weekly retro keys off, and staleness against the current week is
    computed at the API layer (same pattern as `carried_forward`)."""
    today = today or datetime.now().date().isoformat()
    current_week_start = week_start_date(date_cls.fromisoformat(today)).isoformat()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT last_run_week_start FROM week_rollover WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row and row["last_run_week_start"] == current_week_start:
            return WeekRolloverResult(ran=False, cleared_count=0)

        stale_rows = conn.execute(
            "SELECT id FROM tasks WHERE user_id = ? AND is_this_week = 1 AND status != ?",
            (user_id, STATUS_COMPLETED),
        ).fetchall()
        for r in stale_rows:
            conn.execute("UPDATE tasks SET is_this_week = 0 WHERE id = ?", (r["id"],))

        conn.execute(
            "UPDATE tasks SET is_this_week = 0 WHERE user_id = ? AND is_this_week = 1 AND status = ?",
            (user_id, STATUS_COMPLETED),
        )
        conn.execute(
            "INSERT INTO week_rollover (user_id, last_run_week_start) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_run_week_start = excluded.last_run_week_start",
            (user_id, current_week_start),
        )
        conn.commit()

    return WeekRolloverResult(ran=True, cleared_count=len(stale_rows))
