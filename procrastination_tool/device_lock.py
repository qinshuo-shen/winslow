"""
Cross-device write-safety guard for the "two Macs, each running the app
independently, data/sessions.db synced between them via Syncthing" model
(2026-08-11, second same-day follow-up -- see the wiki's Board-redesign
synthesis page for the full context). This app's persistence is a single
SQLite file; two live instances writing to it at once, or one starting
against a copy a sync tool hasn't finished writing yet, is a real
corruption/data-loss risk, not a theoretical one -- this project's own
history already has iCloud Drive silently reverting a different file with
no warning at all.

This module can't detect "has Syncthing finished syncing" -- no such
signal exists to hook into from here. What it CAN do is catch the single
most common real mistake: forgetting to fully quit the app on one machine
before starting it on the other. That only needs one fact, stored INSIDE
the same file that's being synced (a `device_lock` table, not a separate
sidecar file) so the lock state travels with the data atomically instead
of risking its own out-of-sync race against a second file: which hostname
most recently opened the app, and whether that session closed cleanly.

Deliberately hostname-scoped, not process-scoped: same-machine multi-
process access (e.g. running the web server and the `focus` CLI on the
same Mac at once) is a different, lesser concern already reasonably
handled by SQLite's own file locking -- this guard exists specifically for
the cross-device case, where SQLite's locking can't help at all (the two
processes never see each other's file locks, only their synced-after-the-
fact copies of the file).
"""
import socket
import sqlite3
from contextlib import closing
from datetime import datetime

from .config import SESSION_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS device_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    hostname TEXT,
    opened_at TEXT,
    closed_at TEXT,
    is_running INTEGER NOT NULL DEFAULT 0
)
"""


class DeviceLockError(RuntimeError):
    """Raised by acquire() when it looks unsafe to start against the
    current data/sessions.db -- see this module's docstring."""


def _connect() -> sqlite3.Connection:
    # A short busy_timeout so a concurrent same-host access doesn't hang
    # indefinitely; a genuinely corrupted/half-synced file should still
    # raise sqlite3.DatabaseError here, which the caller treats as unsafe
    # to proceed past rather than silently continuing on garbage data.
    conn = sqlite3.connect(SESSION_DB_PATH, timeout=5)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def acquire(force: bool = False) -> None:
    """Call once at process startup, before anything else touches the DB.

    Raises DeviceLockError if another hostname's session looks still-open
    (or crashed without a clean close) -- the caller should treat this as
    fatal (refuse to start), not retry silently. Pass force=True only
    after confirming directly that the other machine genuinely isn't
    running the app right now (see PROCRASTINATION_TOOL_FORCE_UNLOCK in
    api/main.py and `focus`'s CLI entry point)."""
    hostname = socket.gethostname()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT hostname, opened_at, is_running FROM device_lock WHERE id = 1"
        ).fetchone()

        if row is not None:
            prev_hostname, prev_opened_at, is_running = row
            if is_running and prev_hostname != hostname and not force:
                raise DeviceLockError(
                    f"data/sessions.db was last opened by {prev_hostname!r} at "
                    f"{prev_opened_at} and was never marked closed cleanly. If "
                    f"{prev_hostname!r} is still running this app, stop it there "
                    f"first, wait for the sync to finish, then start here. If it "
                    f"crashed or was force-quit and you're SURE it isn't running, "
                    f"set PROCRASTINATION_TOOL_FORCE_UNLOCK=1 to override once."
                )
            if is_running and prev_hostname == hostname:
                print(
                    "[device_lock] Warning: this machine's last session didn't "
                    "close cleanly (crash?) -- continuing anyway, same machine."
                )

        conn.execute(
            "INSERT INTO device_lock (id, hostname, opened_at, closed_at, is_running) "
            "VALUES (1, ?, ?, NULL, 1) "
            "ON CONFLICT(id) DO UPDATE SET "
            "hostname = excluded.hostname, opened_at = excluded.opened_at, is_running = 1",
            (hostname, datetime.now().isoformat()),
        )
        conn.commit()


def release() -> None:
    """Call on graceful shutdown -- marks the lock closed so the OTHER
    machine's next acquire() doesn't have to force through it. Scoped to
    this hostname (WHERE hostname = ?) so a stale release from a process
    that never actually held the lock can't clobber a real one."""
    hostname = socket.gethostname()
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE device_lock SET is_running = 0, closed_at = ? "
            "WHERE id = 1 AND hostname = ?",
            (datetime.now().isoformat(), hostname),
        )
        conn.commit()
