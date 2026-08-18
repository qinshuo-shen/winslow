"""
Virtual daily standup (Scrum-lite feature set) -- an on-demand, single-shot
AI-generated response: by default a short, forward-looking note about
today's plan, or -- if the user typed a question into the same box -- a
direct answer to it. This also absorbed the AI PM-agent's backlog-review
job (see pm_agent.py, now unregistered but left on disk): rather than a
second AI feature, one on-demand box now covers both "what's on deck
today" and "what should I reprioritize" style questions.

Strictly forward-looking by design, not just by prompt instruction, for
the DEFAULT (no-question) note specifically: the weekly Retro (see
evaluation.py's generate_weekly_retro()) is deliberately kept at
week-granularity because a psychologist consult flagged day-by-day
comparison as rumination bait for this user. This module never imports
`evaluation` at all -- historical/retro/mood data is structurally
unreachable here, not merely unused. A user-typed question is a different
interaction shape, though: the risk was specifically *unprompted* daily
comparisons, not the user asking on purpose (the same distinction that
made PM-agent's own on-demand carry-over-risk analysis acceptable) -- see
_SYSTEM_PROMPT for how the two modes differ. `daily_standups` still has no
column to hold the question text in, so "the question field is ephemeral"
stays a schema fact, not a convention someone could accidentally violate.

The `anthropic` package is imported lazily, inside AnthropicStandupClient.
__init__ only -- same reasoning as pm_agent.py: this module, FakeStandup
Client, and STANDUP_MOCK=1 local dev all work with the dependency
uninstalled and no API key at all.
"""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from typing import Optional, Protocol

from . import tasks
from .config import ANTHROPIC_API_KEY, SESSION_DB_PATH, STANDUP_MOCK, STANDUP_MODEL

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_standups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    note_date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    model_used TEXT NOT NULL,
    note_markdown TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_standups_note_date ON daily_standups(note_date);
"""

# A single personal user's realistic open-task count is well under this; it
# exists purely as a hard ceiling on request size, oldest tasks dropped
# first -- same constant/reasoning as pm_agent.py's own _MAX_BACKLOG_TASKS.
_MAX_BACKLOG_TASKS = 150

# Nullable for the same reason every other module's multi-user column is:
# ALTER TABLE can't add NOT NULL with no default to a table that already
# has rows. scripts/bootstrap_multiuser.py backfills existing NULL rows to
# the owner's account.
_NEW_COLUMNS = {"user_id": "INTEGER"}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(daily_standups)")}
    for name, coltype in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE daily_standups ADD COLUMN {name} {coltype}")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn


class StandupNotConfiguredError(RuntimeError):
    pass


@dataclass
class StandupNote:
    generated_at: datetime
    model_used: str
    note_date: date_cls
    note: str


class StandupClient(Protocol):
    def generate_note(self, snapshot: dict) -> str: ...


_SYSTEM_PROMPT = """You are a calm, practical planning assistant embedded in \
Winslow, a personal task-management tool built by its sole user to manage \
executive dysfunction alongside ADHD, depression, and OCD. You're shown \
today's date and the user's full current open backlog (not just what's \
pulled into Today), plus an optional question or note they typed for this \
check-in.

If NO question was given, write a short, forward-looking standup note: \
what's worth focusing on today, and a single gentle suggested focus. In \
this default mode specifically:
- This is about TODAY ONLY. Never mention "yesterday," never describe what \
was or wasn't completed previously, never make any before/now comparison, \
even a neutral one.
- If a task is marked as carried over, describe it only as something \
currently on the list -- never mention how long it's been open, never use \
"days" or duration language, never frame it as something previously missed.
- Keep it short: 2-4 short paragraphs, or a short paragraph plus a brief \
bulleted list. It should read as one cohesive note, not a data dump.

If a question WAS given, answer it directly and helpfully instead -- this \
covers backlog-review questions too ("what should I reprioritize," "what's \
been sitting a while," "what's blocking me and what's a small first step"), \
not just literal blockers. Since the user is asking on purpose here, not \
receiving an unprompted comparison, you may reference how long a task has \
been open (its created_at date, or its carried_forward flag) if that's \
genuinely relevant to answering the question -- but always describe it \
neutrally ("this has been on the list a while"), never as a judgment.

Tone rules, followed strictly in both modes:
- Never use streak language, shame language, or "you still haven't..." \
framing.
- Prefer noticing over judging: "this has been in the pool for a while" \
beats "you're avoiding this."
- Don't lecture or diagnose -- one concrete, low-effort suggestion beats a \
checklist.

Return only the response itself as markdown text."""

_STANDUP_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"note": {"type": "string"}},
    "required": ["note"],
    "additionalProperties": False,
}


class AnthropicStandupClient:
    """A single-shot, non-agentic structured-output call -- same mechanism
    as pm_agent.AnthropicPMAgentClient (plain messages.create() with
    output_config.format, response parsed manually)."""

    def __init__(self, api_key: str, model: str):
        import anthropic  # lazy: only needed when this class is actually instantiated

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate_note(self, snapshot: dict) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(snapshot)}],
            output_config={"format": {"type": "json_schema", "schema": _STANDUP_RESPONSE_SCHEMA}},
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return json.loads(text)["note"] if text else ""


class FakeStandupClient:
    """Deterministic canned markdown -- zero network calls, zero cost. Used
    whenever STANDUP_MOCK=1 (even with no API key set at all). The canned
    text itself avoids "yesterday"/duration language, so mock testing
    doesn't normalize the framing this module is built to avoid."""

    def generate_note(self, snapshot: dict) -> str:
        n = len(snapshot.get("open_backlog", []))
        question = snapshot.get("question")
        if question:
            return (
                f"(mock) STANDUP_MOCK=1 -- canned answer, no API call made.\n\n"
                f'You asked: "{question}"\n\n'
                f"There are {n} open task(s) in your backlog right now."
            )
        return (
            f"(mock) STANDUP_MOCK=1 -- canned note, no API call made.\n\n"
            f"You've got {n} open task(s) in your backlog.\n\n"
            f"Suggested focus: pick the smallest one and start there."
        )


def is_configured() -> bool:
    return bool(ANTHROPIC_API_KEY)


def get_client() -> StandupClient:
    """FastAPI route calls this directly (not via Depends()) so
    StandupNotConfiguredError stays catchable in the same try block --
    identical reasoning to pm_agent.get_client()'s docstring."""
    if STANDUP_MOCK:
        return FakeStandupClient()
    if not is_configured():
        raise StandupNotConfiguredError(
            "ANTHROPIC_API_KEY not set in .env (or set STANDUP_MOCK=1 for local dev)"
        )
    return AnthropicStandupClient(api_key=ANTHROPIC_API_KEY, model=STANDUP_MODEL)


def build_standup_snapshot(user_id: int, question: str) -> dict:
    """The full open backlog (every non-completed, non-draft task, not just
    today's) -- needed so a question can actually be answered, mirroring
    pm_agent.build_snapshot()'s own backlog shape and cap. Still no task
    `notes` (privacy, same boundary as pm_agent), still no import of
    `evaluation` anywhere in this module -- daily/weekly retro rollups and
    mood data stay structurally unreachable; only per-task `created_at`/
    `carried_forward` are newly exposed here, not history in aggregate.
    See _SYSTEM_PROMPT for why that's an acceptable line to draw."""
    all_tasks = tasks.list_all_tasks(user_id)
    today_str = date_cls.today().isoformat()

    open_tasks = [
        t for t in all_tasks
        if t.status != tasks.STATUS_COMPLETED and not t.is_draft
    ]
    open_tasks.sort(key=lambda t: t.created_at)
    if len(open_tasks) > _MAX_BACKLOG_TASKS:
        open_tasks = open_tasks[-_MAX_BACKLOG_TASKS:]

    return {
        "today": today_str,
        "open_backlog": [
            {
                "id": t.id,
                "name": t.name,
                "priority": t.priority,
                "effort_minutes": t.effort_minutes,
                "is_today": t.is_today,
                "is_this_week": t.is_this_week,
                "specific_project": t.specific_project,
                "tags": t.tags,
                "created_at": t.created_at.date().isoformat(),
                "carried_forward": t.carried_forward_date == today_str,
            }
            for t in open_tasks
        ],
        "question": question,
    }


def generate_standup(user_id: int, client: StandupClient, question: str = "") -> StandupNote:
    """Builds the snapshot, calls the client, persists ONLY the resulting
    note (never `question` -- see the module docstring for why there's no
    column for it at all), keyed by today's note_date."""
    snapshot = build_standup_snapshot(user_id, question)
    note_text = client.generate_note(snapshot)
    generated_at = datetime.now()
    note_date = date_cls.today()
    model_used = STANDUP_MODEL if isinstance(client, AnthropicStandupClient) else "mock"

    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO daily_standups (user_id, note_date, generated_at, model_used, "
            "note_markdown) VALUES (?, ?, ?, ?, ?)",
            (user_id, note_date.isoformat(), generated_at.isoformat(), model_used, note_text),
        )
        conn.commit()

    return StandupNote(
        generated_at=generated_at, model_used=model_used, note_date=note_date, note=note_text,
    )


def get_today_note(user_id: int) -> Optional[StandupNote]:
    """The most recently generated note for TODAY specifically (not "most
    recent ever," unlike pm_agent.get_last_review()) -- "last generation
    today wins" if regenerated more than once, and a genuine midnight
    rollover needs no special handling since date.today() is re-evaluated
    on every call, nothing is cached."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM daily_standups WHERE user_id = ? AND note_date = ? "
            "ORDER BY id DESC LIMIT 1",
            (user_id, date_cls.today().isoformat()),
        ).fetchone()
    if row is None:
        return None
    return StandupNote(
        generated_at=datetime.fromisoformat(row["generated_at"]),
        model_used=row["model_used"],
        note_date=date_cls.fromisoformat(row["note_date"]),
        note=row["note_markdown"],
    )
