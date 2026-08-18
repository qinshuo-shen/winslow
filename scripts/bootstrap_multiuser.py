"""
One-time migration for the existing, already-populated data/sessions.db --
creates real per-user accounts and backfills every pre-existing row (the
owner's real history) to the owner's new account. Run this once, directly
against whichever machine holds the authoritative data/sessions.db (see
the README's "Adding a second user" section for the full sequence,
including doing this against a scratch copy first).

Safe to re-run: every step below checks whether it's already applied
before touching anything, and a fresh backup copy of the DB is taken
before any write. A brand-new, empty database needs none of this --
every module's own `CREATE TABLE IF NOT EXISTS` already creates the
multi-user schema (user_id columns/constraints) directly; there's nothing
old-shaped to migrate or backfill.
"""
import getpass
import shutil
import sqlite3
from contextlib import closing

from procrastination_tool import auth, evaluation, focus_timer, projects, push_notifications, standup, tasks
from procrastination_tool.config import SESSION_DB_PATH

# (module, table) pairs whose user_id column is a simple nullable
# ALTER TABLE ADD COLUMN, already applied lazily by the module's own
# _connect() (see each module's _NEW_COLUMNS/_ensure_columns) -- this
# script only needs to trigger that connect, then backfill the NULLs.
_SIMPLE_TABLES = [
    (tasks, "tasks"),
    (projects, "projects"),
    (focus_timer, "sessions"),
    (evaluation, "mood_entries"),
    (standup, "daily_standups"),
    (push_notifications, "push_subscriptions"),
]


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(SESSION_DB_PATH)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _backup() -> None:
    if not SESSION_DB_PATH.exists():
        return
    backup_path = SESSION_DB_PATH.with_name(SESSION_DB_PATH.name + ".pre-migration-backup")
    if backup_path.exists():
        print(f"Backup already exists at {backup_path} -- not overwriting it.")
        return
    shutil.copy2(SESSION_DB_PATH, backup_path)
    print(f"Backed up {SESSION_DB_PATH} -> {backup_path}")


def _get_or_create_owner() -> auth.User:
    owner = auth.get_owner_user()
    if owner is not None:
        print(f"Owner account already exists: {owner.username!r} -- existing data backfills to it.")
        return owner
    print("No accounts exist yet. Create the OWNER account first -- it inherits every")
    print("pre-existing task/session/evaluation already in this database.")
    username = input("Owner username: ").strip()
    password = getpass.getpass("Owner password: ")
    owner = auth.create_user(username, password)
    print(f"Created owner account {owner.username!r} (id={owner.id}).")
    return owner


def _maybe_create_second_account() -> None:
    with closing(_connect()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count >= 2:
        return
    if input("Create a second account now (e.g. your friend's)? [y/N]: ").strip().lower() != "y":
        print("Skipped -- run scripts/create_user.py later to add it.")
        return
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    user = auth.create_user(username, password)
    print(f"Created account {user.username!r} (id={user.id}).")


def _backfill_simple_tables(owner_id: int) -> None:
    for module, table in _SIMPLE_TABLES:
        module._connect().close()  # triggers that module's own guarded ALTER TABLE
        with closing(_connect()) as conn:
            cur = conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (owner_id,))
            conn.commit()
            if cur.rowcount:
                print(f"{table}: backfilled {cur.rowcount} row(s) to the owner's account.")


def _rebuild_tags(conn: sqlite3.Connection, owner_id: int) -> None:
    if not _table_exists(conn, "tags") or _has_column(conn, "tags", "user_id"):
        return
    conn.execute(
        "CREATE TABLE tags_new ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL, "
        "parent_id INTEGER REFERENCES tags(id), UNIQUE(user_id, name))"
    )
    rows = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    conn.execute(
        "INSERT INTO tags_new (id, user_id, name, parent_id) SELECT id, ?, name, parent_id FROM tags",
        (owner_id,),
    )
    conn.execute("DROP TABLE tags")
    conn.execute("ALTER TABLE tags_new RENAME TO tags")
    print(f"tags: rebuilt with UNIQUE(user_id, name), backfilled {rows} row(s).")


def _rebuild_singleton_rollover(conn: sqlite3.Connection, table: str, date_column: str, owner_id: int) -> None:
    if not _table_exists(conn, table) or _has_column(conn, table, "user_id"):
        return
    conn.execute(f"CREATE TABLE {table}_new (user_id INTEGER PRIMARY KEY, {date_column} TEXT NOT NULL)")
    row = conn.execute(f"SELECT {date_column} FROM {table} WHERE id = 1").fetchone()
    if row:
        conn.execute(f"INSERT INTO {table}_new (user_id, {date_column}) VALUES (?, ?)", (owner_id, row[0]))
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    print(f"{table}: rebuilt as one row per user, backfilled {1 if row else 0} row(s).")


def _rebuild_daily_evaluations(conn: sqlite3.Connection, owner_id: int) -> None:
    if not _table_exists(conn, "daily_evaluations") or _has_column(conn, "daily_evaluations", "user_id"):
        return
    conn.execute(
        "CREATE TABLE daily_evaluations_new ("
        "user_id INTEGER NOT NULL, date TEXT NOT NULL, generated_at TEXT NOT NULL, "
        "sessions_count INTEGER NOT NULL, focused_minutes REAL NOT NULL, completion_rate REAL, "
        "tasks_completed_count INTEGER NOT NULL, runes_earned INTEGER NOT NULL, mood_avg REAL, "
        "summary_json TEXT NOT NULL, PRIMARY KEY (user_id, date))"
    )
    rows = conn.execute("SELECT COUNT(*) FROM daily_evaluations").fetchone()[0]
    conn.execute(
        "INSERT INTO daily_evaluations_new (user_id, date, generated_at, sessions_count, "
        "focused_minutes, completion_rate, tasks_completed_count, runes_earned, mood_avg, "
        "summary_json) SELECT ?, date, generated_at, sessions_count, focused_minutes, "
        "completion_rate, tasks_completed_count, runes_earned, mood_avg, summary_json "
        "FROM daily_evaluations",
        (owner_id,),
    )
    conn.execute("DROP TABLE daily_evaluations")
    conn.execute("ALTER TABLE daily_evaluations_new RENAME TO daily_evaluations")
    print(f"daily_evaluations: rebuilt with PRIMARY KEY (user_id, date), backfilled {rows} row(s).")


def _rebuild_weekly_retros(conn: sqlite3.Connection, owner_id: int) -> None:
    if not _table_exists(conn, "weekly_retros") or _has_column(conn, "weekly_retros", "user_id"):
        return
    conn.execute(
        "CREATE TABLE weekly_retros_new ("
        "user_id INTEGER NOT NULL, week_start TEXT NOT NULL, week_end TEXT NOT NULL, "
        "generated_at TEXT NOT NULL, sessions_count INTEGER NOT NULL, focused_minutes REAL NOT NULL, "
        "tasks_completed_count INTEGER NOT NULL, committed_count INTEGER NOT NULL, "
        "committed_completed_count INTEGER NOT NULL, mood_avg REAL, summary_json TEXT NOT NULL, "
        "PRIMARY KEY (user_id, week_start))"
    )
    rows = conn.execute("SELECT COUNT(*) FROM weekly_retros").fetchone()[0]
    conn.execute(
        "INSERT INTO weekly_retros_new (user_id, week_start, week_end, generated_at, "
        "sessions_count, focused_minutes, tasks_completed_count, committed_count, "
        "committed_completed_count, mood_avg, summary_json) SELECT ?, week_start, week_end, "
        "generated_at, sessions_count, focused_minutes, tasks_completed_count, committed_count, "
        "committed_completed_count, mood_avg, summary_json FROM weekly_retros",
        (owner_id,),
    )
    conn.execute("DROP TABLE weekly_retros")
    conn.execute("ALTER TABLE weekly_retros_new RENAME TO weekly_retros")
    print(f"weekly_retros: rebuilt with PRIMARY KEY (user_id, week_start), backfilled {rows} row(s).")


def main() -> None:
    _backup()

    owner = _get_or_create_owner()
    _maybe_create_second_account()

    _backfill_simple_tables(owner.id)

    with closing(_connect()) as conn:
        _rebuild_tags(conn, owner.id)
        _rebuild_singleton_rollover(conn, "today_rollover", "last_run_date", owner.id)
        _rebuild_singleton_rollover(conn, "week_rollover", "last_run_week_start", owner.id)
        _rebuild_daily_evaluations(conn, owner.id)
        _rebuild_weekly_retros(conn, owner.id)
        conn.commit()

    print("\nDone. Every pre-existing row now belongs to the owner's account.")
    print("Run scripts/create_user.py to add any further accounts, or re-run this")
    print("script later -- every step above is a no-op once already applied.")


if __name__ == "__main__":
    main()
