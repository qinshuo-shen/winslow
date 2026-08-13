"""
AI PM-agent (Scrum-lite feature set) -- reviews the current backlog plus
recent evaluation/retro history and returns SUGGESTIONS, never applies
anything itself. This module has no write path to `tasks` at all: a
suggestion's `suggested_action` is a subset of the same fields
BacklogTaskUpdateRequest already accepts, and "applying" one in the
frontend is just an ordinary PATCH /api/backlog/{id} -- identical to any
manual Board edit. That's the actual mechanism enforcing "suggest, never
auto-act," not a convention someone could accidentally violate later.

The `anthropic` package (pyproject.toml's optional `ai` extra) is imported
lazily, inside AnthropicPMAgentClient.__init__ only -- so this module,
FakePMAgentClient, and PM_AGENT_MOCK=1 local dev all work with the
dependency uninstalled and no API key at all.
"""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime
from typing import List, Optional, Protocol

from . import evaluation, tasks
from .config import ANTHROPIC_API_KEY, PM_AGENT_MOCK, PM_AGENT_MODEL, SESSION_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pm_agent_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    model_used TEXT NOT NULL,
    suggestions_json TEXT NOT NULL
);
"""

# A single personal user's realistic open-task count is well under this;
# it exists purely as a hard ceiling on request size, oldest tasks dropped
# first (list_all_tasks() is already sorted oldest-first within this
# filter after the sort below).
_MAX_BACKLOG_TASKS = 150


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


class PMAgentNotConfiguredError(RuntimeError):
    pass


@dataclass
class PMSuggestedAction:
    """A 1:1 subset of BacklogTaskUpdateRequest's fields -- deliberately
    not the full set (no `name`/`notes` rewrite, no `status`/`tags`
    changes) since a planning suggestion should reprioritize/reschedule a
    task, not rewrite its content."""

    priority: Optional[str] = None
    is_today: Optional[bool] = None
    is_this_week: Optional[bool] = None


@dataclass
class PMSuggestion:
    id: str
    kind: str
    task_id: Optional[int]
    title: str
    rationale: str
    suggested_action: Optional[PMSuggestedAction] = None


class PMAgentClient(Protocol):
    def get_suggestions(self, snapshot: dict) -> List[PMSuggestion]: ...


_SYSTEM_PROMPT = """You are a calm, practical planning assistant embedded in \
Winslow, a personal task-management tool built by its sole user to manage \
executive dysfunction alongside ADHD, depression, and OCD. You review a \
snapshot of their current backlog and recent history and SUGGEST things \
worth their attention -- you never state a suggestion as already applied, \
and you have no ability to change anything yourself.

Tone rules, followed strictly:
- Never use streak language, shame language, or "you failed to..." framing.
- Never imply a pattern is a personal failing -- describe what the data \
shows, not what it means about the person.
- Prefer noticing over judging: "this has been in the pool for N weeks" \
beats "you're avoiding this."
- Keep rationale short (1-2 sentences) and concrete, tied to the actual \
data in the snapshot, not generic productivity advice.

For each suggestion, decide whether a concrete action would help \
(kind: "reprioritize" -- change priority/is_today/is_this_week; \
kind: "carry_over_risk" -- flag a task that's been committed repeatedly \
without completion; kind: "effort_mismatch" -- flag a quadrant/effort \
mismatch; kind: "risk_flag" -- flag something worth attention with no \
specific field change; kind: "general_note" -- an observation with no \
task-specific action at all). Only set suggested_action when a concrete \
field change would genuinely help -- many good suggestions have none.

Return between 0 and 8 suggestions. Fewer, well-grounded suggestions are \
better than many generic ones. If the backlog looks genuinely fine, say so \
with a single general_note suggestion rather than inventing concerns."""

_SUGGESTION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "A short unique slug for this suggestion."},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "reprioritize", "risk_flag", "carry_over_risk",
                            "effort_mismatch", "general_note",
                        ],
                    },
                    "task_id": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "The backlog task this suggestion is about, or null for a general note.",
                    },
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "suggested_action": {
                        "anyOf": [
                            {"type": "null"},
                            {
                                "type": "object",
                                "properties": {
                                    "priority": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                    "is_today": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                                    "is_this_week": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                                },
                                "required": ["priority", "is_today", "is_this_week"],
                                "additionalProperties": False,
                            },
                        ],
                    },
                },
                "required": ["id", "kind", "task_id", "title", "rationale", "suggested_action"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


class AnthropicPMAgentClient:
    """Real client. A single-shot, non-agentic structured-output call --
    not a tool-use loop, so a plain `messages.create()` with
    `output_config.format` is the correct primitive here (see
    shared Claude API reference: "output_config.format constrains the
    Messages API response format"). Response text is parsed manually
    rather than via the SDK's `.parse()` convenience wrapper, whose exact
    Python calling convention for a raw (non-Pydantic) JSON schema isn't
    something to guess at -- `create()` + `output_config.format` is the
    explicitly documented, verified-correct mechanism regardless."""

    def __init__(self, api_key: str, model: str):
        import anthropic  # lazy: only needed when this class is actually instantiated

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def get_suggestions(self, snapshot: dict) -> List[PMSuggestion]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(snapshot)}],
            output_config={"format": {"type": "json_schema", "schema": _SUGGESTION_RESPONSE_SCHEMA}},
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        data = json.loads(text) if text else {"suggestions": []}
        return [_suggestion_from_dict(item) for item in data.get("suggestions", [])]


class FakePMAgentClient:
    """Deterministic canned suggestions -- zero network calls, zero cost.
    Used whenever PM_AGENT_MOCK=1 (even with no API key set at all), so
    the full review/apply/dismiss UI flow can be exercised in dev without
    ever touching the real API."""

    def get_suggestions(self, snapshot: dict) -> List[PMSuggestion]:
        backlog = snapshot.get("backlog", [])
        suggestions = [
            PMSuggestion(
                id="mock-overview", kind="general_note", task_id=None,
                title="(mock) Backlog snapshot received",
                rationale=(
                    f"PM_AGENT_MOCK=1 -- canned response, no API call made. "
                    f"{len(backlog)} open task(s) in this snapshot."
                ),
                suggested_action=None,
            )
        ]
        if backlog:
            first = backlog[0]
            suggestions.append(
                PMSuggestion(
                    id="mock-reprioritize", kind="reprioritize", task_id=first["id"],
                    title=f"(mock) Consider pulling '{first['name']}' into today",
                    rationale="(mock) Deterministic canned suggestion for PM_AGENT_MOCK=1 testing.",
                    suggested_action=PMSuggestedAction(is_today=True),
                )
            )
        return suggestions


def is_configured() -> bool:
    return bool(ANTHROPIC_API_KEY)


def get_client() -> PMAgentClient:
    """FastAPI dependency (Depends(get_client)). Returns FakePMAgentClient
    whenever PM_AGENT_MOCK=1, the real client if configured, else raises --
    surfaced as HTTP 400 by the router, same convention character.py's
    ValueError->400 already uses in this codebase."""
    if PM_AGENT_MOCK:
        return FakePMAgentClient()
    if not is_configured():
        raise PMAgentNotConfiguredError(
            "ANTHROPIC_API_KEY not set in .env (or set PM_AGENT_MOCK=1 for local dev)"
        )
    return AnthropicPMAgentClient(api_key=ANTHROPIC_API_KEY, model=PM_AGENT_MODEL)


def build_snapshot(days_history: int = 7, weeks_history: int = 6) -> dict:
    """Assembles the exact JSON sent to the model. Task `notes` are
    deliberately NOT included (confirmed privacy decision -- notes may
    reference sensitive personal-life or health context, not just work);
    only structural fields go out. Mood history is aggregate `mood_avg`
    numbers only, never mood_entries free-text -- same boundary the
    end-of-day reminder already respects. Backlog capped at
    _MAX_BACKLOG_TASKS, oldest tasks dropped first."""
    open_tasks = [t for t in tasks.list_all_tasks() if t.status != tasks.STATUS_COMPLETED]
    open_tasks.sort(key=lambda t: t.created_at)
    if len(open_tasks) > _MAX_BACKLOG_TASKS:
        open_tasks = open_tasks[-_MAX_BACKLOG_TASKS:]

    backlog = [
        {
            "id": t.id,
            "name": t.name,
            "priority": t.priority,
            "effort_minutes": t.effort_minutes,
            "status": t.status,
            "is_today": t.is_today,
            "is_this_week": t.is_this_week,
            "specific_project": t.specific_project,
            "tags": t.tags,
            "created_at": t.created_at.date().isoformat(),
        }
        for t in open_tasks
    ]

    weekly_history = [
        {
            "week_start": r.week_start.isoformat(),
            "sessions_count": r.sessions_count,
            "focused_minutes": r.focused_minutes,
            "tasks_completed_count": r.tasks_completed_count,
            "committed_count": r.committed_count,
            "committed_completed_count": r.committed_completed_count,
            "mood_avg": r.mood_avg,
        }
        for r in evaluation.list_weekly_retros(weeks_history)
    ]

    daily_history = [
        {
            "date": e.date.isoformat(),
            "sessions_count": e.sessions_count,
            "focused_minutes": e.focused_minutes,
            "tasks_completed_count": e.tasks_completed_count,
            "mood_avg": e.mood_avg,
        }
        for e in evaluation.list_evaluations(days_history)
    ]

    return {
        "today": date_cls.today().isoformat(),
        "backlog": backlog,
        "weekly_history": weekly_history,
        "daily_history": daily_history,
    }


def _suggestion_from_dict(item: dict) -> PMSuggestion:
    action = item.get("suggested_action")
    return PMSuggestion(
        id=item["id"], kind=item["kind"], task_id=item.get("task_id"),
        title=item["title"], rationale=item["rationale"],
        suggested_action=(
            PMSuggestedAction(
                priority=action.get("priority"), is_today=action.get("is_today"),
                is_this_week=action.get("is_this_week"),
            ) if action else None
        ),
    )


def _suggestion_to_dict(s: PMSuggestion) -> dict:
    return {
        "id": s.id, "kind": s.kind, "task_id": s.task_id,
        "title": s.title, "rationale": s.rationale,
        "suggested_action": (
            {
                "priority": s.suggested_action.priority,
                "is_today": s.suggested_action.is_today,
                "is_this_week": s.suggested_action.is_this_week,
            } if s.suggested_action else None
        ),
    }


def review_backlog(client: PMAgentClient) -> List[PMSuggestion]:
    """Builds the snapshot, calls the client, persists the result (same
    "so a refresh doesn't lose it, and so it's not silently re-calling a
    paid API" reasoning as daily_evaluations), and returns the
    suggestions. Never writes to `tasks` -- see the module docstring."""
    snapshot = build_snapshot()
    suggestions = client.get_suggestions(snapshot)
    generated_at = datetime.now()
    model_used = PM_AGENT_MODEL if isinstance(client, AnthropicPMAgentClient) else "mock"

    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO pm_agent_reviews (generated_at, model_used, suggestions_json) "
            "VALUES (?, ?, ?)",
            (
                generated_at.isoformat(), model_used,
                json.dumps([_suggestion_to_dict(s) for s in suggestions]),
            ),
        )
        conn.commit()

    return suggestions


@dataclass
class PMReview:
    generated_at: datetime
    model_used: str
    suggestions: List[PMSuggestion] = field(default_factory=list)


def get_last_review() -> Optional[PMReview]:
    """The most recently persisted review, if any -- lets the frontend show
    the last result on page load without forcing a fresh (paid) call."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM pm_agent_reviews ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    items = json.loads(row["suggestions_json"])
    return PMReview(
        generated_at=datetime.fromisoformat(row["generated_at"]),
        model_used=row["model_used"],
        suggestions=[_suggestion_from_dict(i) for i in items],
    )
