"""
Real per-user accounts (multi-user follow-up) -- exactly 2 users expected
(the app owner + one friend), so this is deliberately minimal: username +
password, hashed with bcrypt, backed by an opaque server-side session
token in a cookie. No self-serve signup (see scripts/create_user.py) and
no email-based password *reset* at all -- this project has already tried
and removed an email integration once (see README's Gmail history) and
there's no reason to reintroduce that dependency just for account recovery
on a 2-person app. Changing a password you still remember, while logged
in, is a different thing (see change_password() below) -- deliberately
supported so the app owner is never the one setting or knowing the
friend's password past initial account creation, matching the "private
from the owner too" goal the multi-user work exists for.

Deliberately framework-agnostic (no FastAPI/Request/HTTPException import
here) -- api/deps.py is the one place allowed to know about the HTTP layer,
same split as e.g. standup.StandupNotConfiguredError being a plain
exception the router converts to an HTTPException.

Session tokens are opaque (secrets.token_urlsafe), not JWTs: with only 2
users, instant revocation (a plain DELETE on logout, or "kill every
session for this account") matters more than stateless verification, and a
stateless JWT would need the same server-side denylist table anyway to get
real revocation -- at which point it's the same complexity as this, minus
the instant-kill property. Sessions are long-lived and sliding (see
SESSION_LIFETIME_DAYS) -- two trusted people on their own devices, not a
bank vault.
"""
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import bcrypt

from .config import SESSION_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
"""

# Sliding expiry: any authenticated request pushes expires_at forward by
# this much again (see get_user_by_session_token). 90 days means a device
# that's used at least every ~3 months never has to log back in.
SESSION_LIFETIME_DAYS = 90


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


@dataclass
class User:
    id: int
    username: str


class UsernameTakenError(ValueError):
    pass


def create_user(username: str, password: str) -> User:
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with closing(_connect()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, datetime.now().isoformat()),
            )
        except sqlite3.IntegrityError:
            raise UsernameTakenError(f"Username {username!r} is already taken")
        conn.commit()
        return User(id=cur.lastrowid, username=username)


def get_owner_user() -> Optional[User]:
    """The first account ever created -- what focus_cli.py (the `focus`
    terminal command) always operates as. Only the app owner has shell
    access to the box the DB lives on (the friend is a Tailscale-only web
    client, never SSHes in), so the CLI has no HTTP session/cookie to read
    a user_id from and doesn't need one -- it's always the owner, by
    construction. None if no account has been created yet (before
    scripts/create_user.py has ever been run)."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id, username FROM users ORDER BY id LIMIT 1").fetchone()
    return User(id=row["id"], username=row["username"]) if row else None


def get_user_by_username(username: str) -> Optional[User]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, username FROM users WHERE username = ?", (username,)
        ).fetchone()
    return User(id=row["id"], username=row["username"]) if row else None


def verify_password(username: str, password: str) -> Optional[User]:
    """Returns the User on a correct username+password, None otherwise --
    deliberately the same None for "no such username" as for "wrong
    password" so a login form can't be used to enumerate real usernames."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        return None
    if not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return None
    return User(id=row["id"], username=row["username"])


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires_at = now + timedelta(days=SESSION_LIFETIME_DAYS)
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO auth_sessions (token, user_id, created_at, last_seen_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token, user_id, now.isoformat(), now.isoformat(), expires_at.isoformat()),
        )
        conn.commit()
    return token


def get_user_by_session_token(token: str) -> Optional[User]:
    now = datetime.now()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT auth_sessions.user_id AS user_id, users.username AS username, "
            "auth_sessions.expires_at AS expires_at "
            "FROM auth_sessions JOIN users ON users.id = auth_sessions.user_id "
            "WHERE auth_sessions.token = ?",
            (token,),
        ).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < now:
            conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
            conn.commit()
            return None
        # Sliding expiry: touch last_seen_at/expires_at on every valid use.
        new_expires_at = now + timedelta(days=SESSION_LIFETIME_DAYS)
        conn.execute(
            "UPDATE auth_sessions SET last_seen_at = ?, expires_at = ? WHERE token = ?",
            (now.isoformat(), new_expires_at.isoformat(), token),
        )
        conn.commit()
        return User(id=row["user_id"], username=row["username"])


def revoke_session(token: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
        conn.commit()


class IncorrectPasswordError(ValueError):
    pass


def change_password(
    user_id: int, current_password: str, new_password: str, keep_token: Optional[str] = None
) -> None:
    """Requires the current password (not just an authenticated session) --
    the standard "prove you're still you" check before a credential change,
    same as any real account settings page. Also revokes every OTHER
    session for this account (e.g. a browser profile logged in somewhere
    else, or a stale session from a lost device) -- `keep_token` is the
    caller's own current session, which stays alive so changing your
    password doesn't immediately log you out of the tab you just did it
    from."""
    if not new_password:
        raise ValueError("New password can't be empty")
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ValueError("No such user")
        if not bcrypt.checkpw(current_password.encode("utf-8"), row["password_hash"].encode("utf-8")):
            raise IncorrectPasswordError("Current password is incorrect")

        new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        if keep_token is not None:
            conn.execute(
                "DELETE FROM auth_sessions WHERE user_id = ? AND token != ?",
                (user_id, keep_token),
            )
        else:
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        conn.commit()
