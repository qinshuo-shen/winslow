"""
Web Push notifications -- lets a focus-session outcome reach the user even
when the Winslow tab isn't open/focused or the phone is locked, unlike
notify.py's macOS-only osascript path (dead weight on the deployed headless
Linux VPS) or a same-tab-only browser Notification.

Requires a one-time VAPID keypair (see scripts/generate_vapid_keys.py),
written to data/vapid_private_key.pem -- gitignored, mirroring sessions.db.
The `pywebpush` package (optional `push` extra) is imported lazily inside
send_to_all() only, so nothing else in the app depends on it being
installed, matching pm_agent.py's lazy `import anthropic` convention.
"""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .config import SESSION_DB_PATH, VAPID_CONTACT, VAPID_PRIVATE_KEY_PATH, VAPID_PUBLIC_KEY

_SCHEMA = """
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


@dataclass
class PushSubscription:
    endpoint: str
    p256dh: str
    auth: str


def is_configured() -> bool:
    """Explicit existence check, not just "does VAPID_PUBLIC_KEY parse" --
    py_vapid.Vapid.from_file() silently auto-generates and saves a NEW key
    if the private-key file is missing, which would mint an uncoordinated,
    environment-local keypair on first send rather than failing loudly. A
    missing file must be treated as "not configured," never as "generate
    one now"."""
    return VAPID_PUBLIC_KEY is not None and VAPID_PRIVATE_KEY_PATH.exists()


def add_subscription(endpoint: str, p256dh: str, auth: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO push_subscriptions (endpoint, p256dh, auth, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth",
            (endpoint, p256dh, auth, datetime.now().isoformat()),
        )
        conn.commit()


def remove_subscription(endpoint: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        conn.commit()


def list_subscriptions() -> List[PushSubscription]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions").fetchall()
    return [PushSubscription(endpoint=r["endpoint"], p256dh=r["p256dh"], auth=r["auth"]) for r in rows]


def send_to_all(title: str, body: str, tag: Optional[str] = None) -> None:
    """Best-effort fan-out to every stored subscription. A dead/expired
    subscription (404/410 from the push service) is pruned; any other
    failure -- a non-2xx from the push service, or a request-layer failure
    (timeout, DNS, a malformed endpoint) since pywebpush.webpush() lets
    `requests` exceptions propagate uncaught for anything below the HTTP
    layer, confirmed by reading its source -- is swallowed per-subscription
    so one bad subscriber doesn't block delivery to the rest or crash the
    caller. Same "a missed nudge shouldn't take down the caller" reasoning
    as notify.py."""
    if not is_configured():
        return
    import pywebpush  # lazy: only needed when actually sending
    import requests

    payload = json.dumps({"title": title, "body": body, "tag": tag})
    for sub in list_subscriptions():
        try:
            pywebpush.webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=str(VAPID_PRIVATE_KEY_PATH),
                vapid_claims={"sub": VAPID_CONTACT},
            )
        except pywebpush.WebPushException as ex:
            if ex.response is not None and ex.response.status_code in (404, 410):
                remove_subscription(sub.endpoint)
            # else: swallow -- best-effort, matches notify.py's own precedent.
        except requests.exceptions.RequestException:
            # Network-layer failure below webpush()'s own try/except (it
            # only wraps non-2xx HTTP responses, not connection/timeout/
            # malformed-URL errors) -- swallow for the same reason.
            pass
