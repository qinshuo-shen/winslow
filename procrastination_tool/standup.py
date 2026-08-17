"""
Virtual daily standup (Scrum-lite feature set) -- an on-demand, single-shot
AI-generated note about today's plan: what's open, what's worth focusing
on, and (if given) a way around anything currently blocking the user.

Strictly forward-looking by design, not just by prompt instruction: the
weekly Retro (see evaluation.py's generate_weekly_retro()) is deliberately
kept at week-granularity because a psychologist consult flagged day-by-day
comparison as rumination bait for this user. A daily standup sits close to
that same risk, so this module never imports `evaluation` at all --
historical/completed-task/mood data is structurally unreachable here, not
merely unused -- and `daily_standups` has no column to hold blockers text
in, so "the blockers field is ephemeral" is a schema fact, not a
convention someone could accidentally violate later.

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
    note_date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    model_used TEXT NOT NULL,
    note_markdown TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_standups_note_date ON daily_standups(note_date);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
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
executive dysfunction alongside ADHD, depression, and OCD. You are writing \
today's standup note: a short, forward-looking message about what's open, \
what's worth focusing on today, and (if given) how to work around anything \
currently blocking them.

Strict framing rules, followed at all times:
- This note is about TODAY ONLY. Never mention "yesterday," never describe \
what was or wasn't completed previously, never make any yesterday-vs-today \
or before-vs-now comparison, even a neutral one.
- You have not been given any historical or completed-task data -- only \
today's currently open tasks. Do not speculate about history or invent it.
- If a task is marked as carried over, describe it only as something \
currently on the list -- never mention how long it's been open, never use \
"days" or duration language, never frame it as something previously missed.
- Never use streak language, shame language, or "you still haven't..." \
framing.
- Keep the note short: 2-4 short paragraphs, or a short paragraph plus a \
brief bulleted list. It should read as one cohesive note, not a data dump.
- If there's a blockers note from the user, acknowledge it briefly and \
suggest one concrete, low-effort way to work around or start on it -- \
don't lecture or diagnose.
- End with a single, gentle suggested focus for today -- one thing, not a \
checklist of everything.

Return only the note itself as markdown text."""

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
        n = len(snapshot.get("today_tasks", []))
        blockers = snapshot.get("blockers")
        blockers_line = f"\n\nNoted blocker: {blockers}" if blockers else ""
        return (
            f"(mock) STANDUP_MOCK=1 -- canned note, no API call made.\n\n"
            f"You've got {n} task(s) on today's list."
            f"{blockers_line}\n\nSuggested focus: pick the smallest one and start there."
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


def build_standup_snapshot(blockers: str) -> dict:
    """Strictly forward-looking: only today's currently-open tasks, no
    completed-task data, no daily/weekly history, no mood data, no task
    notes (privacy, same boundary as pm_agent.build_snapshot). Draft
    Roadmap steps are excluded -- not yet committed work. `carried_forward`
    is a bare boolean (today's current state), never a date/duration, so
    there's nothing here to do "days since" math with even if asked to."""
    all_tasks = tasks.list_all_tasks()
    today_str = date_cls.today().isoformat()

    today_tasks = [
        t for t in all_tasks
        if t.is_today and t.status != tasks.STATUS_COMPLETED and not t.is_draft
    ]
    open_backlog_count = sum(
        1 for t in all_tasks
        if not t.is_today and t.status != tasks.STATUS_COMPLETED and not t.is_draft
    )

    return {
        "today": today_str,
        "today_tasks": [
            {
                "id": t.id,
                "name": t.name,
                "priority": t.priority,
                "effort_minutes": t.effort_minutes,
                "specific_project": t.specific_project,
                "tags": t.tags,
                "carried_forward": t.carried_forward_date == today_str,
            }
            for t in today_tasks
        ],
        "open_backlog_count": open_backlog_count,
        "blockers": blockers,
    }


def generate_standup(client: StandupClient, blockers: str = "") -> StandupNote:
    """Builds the snapshot, calls the client, persists ONLY the resulting
    note (never `blockers` -- see the module docstring for why there's no
    column for it at all), keyed by today's note_date."""
    snapshot = build_standup_snapshot(blockers)
    note_text = client.generate_note(snapshot)
    generated_at = datetime.now()
    note_date = date_cls.today()
    model_used = STANDUP_MODEL if isinstance(client, AnthropicStandupClient) else "mock"

    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO daily_standups (note_date, generated_at, model_used, note_markdown) "
            "VALUES (?, ?, ?, ?)",
            (note_date.isoformat(), generated_at.isoformat(), model_used, note_text),
        )
        conn.commit()

    return StandupNote(
        generated_at=generated_at, model_used=model_used, note_date=note_date, note=note_text,
    )


def get_today_note() -> Optional[StandupNote]:
    """The most recently generated note for TODAY specifically (not "most
    recent ever," unlike pm_agent.get_last_review()) -- "last generation
    today wins" if regenerated more than once, and a genuine midnight
    rollover needs no special handling since date.today() is re-evaluated
    on every call, nothing is cached."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM daily_standups WHERE note_date = ? ORDER BY id DESC LIMIT 1",
            (date_cls.today().isoformat(),),
        ).fetchone()
    if row is None:
        return None
    return StandupNote(
        generated_at=datetime.fromisoformat(row["generated_at"]),
        model_used=row["model_used"],
        note_date=date_cls.fromisoformat(row["note_date"]),
        note=row["note_markdown"],
    )
