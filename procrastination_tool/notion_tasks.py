"""
Query and rank actionable tasks from the Notion tasks database.

Schema (as of 2026-08-07, confirmed against the real database -- not
assumed): 'Name' (title), 'Priority' (select, Eisenhower-style categories,
not a simple rank), 'Block' (select, life-area tag), 'Specific Project'
(multi_select), 'Start on' (date), 'Completed' (select: Not Started/In-Progress/
On hold/Completed/Discarded), 'Notes' (rich_text).

**Correction, 2026-08-03, reinforced 2026-08-07**: this date property is the
task's *start* date, not a deadline -- confirmed with the user after the
original "overdue tasks always jump the queue" ranking turned out to be
flooding today's schedule, since most of the backlog's start dates were
already in the past and all of it was getting treated as maximally urgent.
There is no deadline concept anywhere in this database, by design -- the
user deliberately doesn't set due dates on tasks. The property itself was
renamed from 'Date' to 'Start on' 2026-08-07 (and `Task.due`/`TaskSnapshot.due`
renamed to `start_date` here in code to match) after the old ambiguous name
led directly to a real bug: a "due"/"overdue" display in app.py built on top
of what was actually a start date. `sync.py`'s Calendar.app notes tag format
(`"Due:"` line, `"due"` dict key) is deliberately NOT renamed to match --
see sync.py's `_build_notes`/`_parse_notes` docstrings for why (backward
compatibility with already-existing real calendar blocks).

This workspace is on Notion's newer "data sources" API model -- a database
no longer carries `properties` directly; you retrieve its data_sources[0]
id first, then query/retrieve *that*. See config.get_data_source_id().

Design decisions made explicitly with the user, not guessed:
- Only 'Not Started' and 'In-Progress' count as actionable (On hold,
  Discarded, Completed all excluded).
- **(2026-08-02)** Only tasks with a start date set are considered at all --
  undated tasks are left out of auto-scheduling entirely (set 'Start on' in
  Notion if you want something scheduled).
- **(2026-08-03, replacing the original 2026-08-02 rule)** A task is only
  actionable once its start date has arrived: `start_date <= today`.
  Ranking is pure Priority order (see PRIORITY_ORDER) tie-broken by
  earliest start date within the same tier. There is no more "jump the
  queue" override for an old start date; a task that's been sitting
  unstarted for a while doesn't outrank a higher-Priority task that just
  became eligible today.
- **(2026-08-03, same-day follow-up)** Added a *rest-of-week* look-ahead:
  the fetch filter is `start_date <= end of this week` (through Sunday,
  this project's last working day -- see config.WORKING_WEEKDAYS) instead
  of `start_date <= today`, so Tuesday-Friday tasks show up on the calendar
  today instead of trickling in one sync per day. A task still can't
  actually be *placed* before its own start date -- scheduler.schedule_tasks()
  skips any candidate day earlier than the task's `start_date` when
  choosing a slot -- so this only changes *when a task becomes visible for
  scheduling*, not the day it lands on. (scheduler.schedule_tasks() itself
  is no longer invoked automatically as of 2026-08-07 -- see
  block_grid.py's module docstring -- but this fetch-window behavior is
  shared with the still-live manual grid, which has the same "visible
  ahead of its own start date, not placeable before it" property.)
- **(2026-08-03) PRIORITY_ORDER is Effort-first, not Impact-first** --
  Major Projects/Thankless Tasks (High Effort, i.e. higher-concentration
  work) rank ahead of Quick Wins/Fill-ins (Low Effort), with Impact staying
  the tie-break *within* each effort tier. Originally the order was
  Impact-first (Quick Wins -> Major Projects -> Fill-ins -> Thankless), which
  had no concept of concentration/energy at all -- confirmed as a real gap
  when a low-effort Fill-ins task ended up queued ahead of an already
  in-progress Major Projects task on the same day. Since scheduler.py's
  schedule_tasks() is one greedy first-fit pass in this list's order,
  putting High-Effort tasks first is sufficient on its own to give them the
  day's freshest/earliest slots, with Low-Effort tasks naturally filling in
  whatever's left over later.
- **Tasks with no Priority set are excluded from the dashboard entirely**
  (2026-08-02 follow-up, after the first live run): the user uses "No
  Priority" for long-term milestones (e.g. an ongoing research project, a
  personal side project) that aren't meant to be chunked into a single
  short daily block. Give a task a Priority in Notion once it's actually
  actionable in the near term, and it'll start showing up here. **Tried an
  In-Progress-bypasses-Priority exception 2026-08-07, reverted 2026-08-09**:
  it seemed reasonable in the abstract (an in-progress task is a stronger
  actionability signal than an unset field), but in real use it meant
  deliberately-no-Priority long-term milestones ("Paper 2", "PQi data
  analysis pipeline") started showing up as draggable into 45-minute work
  blocks in the React planner, which is exactly what leaving Priority unset
  was meant to prevent. The rule is unqualified again: no Priority, not in
  the dashboard, regardless of status.
- **Duration is derived from Priority, not a flat default** (same
  follow-up, after the first live run's 1-hour-for-everything blocks
  turned out unrealistic): see PRIORITY_DURATION_MINUTES below.
"""
from datetime import date, datetime, timedelta
from typing import List, NamedTuple, Optional

from notion_client import Client
from notion_client.errors import APIErrorCode, APIResponseError

from .config import DEFAULT_TASK_DURATION_MINUTES, NOTION_DATABASE_ID, NOTION_TOKEN

ACTIONABLE_STATUSES = ["Not Started", "In-Progress"]

# Must match the exact option strings in the live 'Priority' select property.
# Effort-first, not Impact-first -- see the module docstring's 2026-08-03
# note for why: heavy/High-Effort tasks get first crack at the day's
# freshest time, light/Low-Effort tasks fill in whatever's left over.
PRIORITY_ORDER = [
    "Major Projects (High Impact-High Effort)",
    "Thankless Tasks (Low Impact-High Effort)",
    "Quick Wins (High Impact-Low Effort)",
    "Fill-ins (Low Impact-Low Effort)",
]

# Rough, adjustable defaults -- "Low Effort" categories get short blocks,
# "High Effort" categories get longer ones. No per-task Estimated Duration
# property exists in Notion yet; this is the zero-extra-data-entry
# improvement over a flat 60 minutes for every task. Change these numbers
# directly if they don't feel right after a week of real use.
PRIORITY_DURATION_MINUTES = {
    "Quick Wins (High Impact-Low Effort)": 30,
    "Major Projects (High Impact-High Effort)": 120,
    "Fill-ins (Low Impact-Low Effort)": 30,
    "Thankless Tasks (Low Impact-High Effort)": 90,
}

# "Light" = the two Low-Effort categories -- confirmed with the user
# 2026-08-02: Sunday is scheduled into a separate, narrower window (see
# config.SUNDAY_START_HOUR/END_HOUR) and only these are ever placed there.
# Major Projects/Thankless Tasks never land on Sunday, even if overdue --
# they roll to the next available weekday instead (see scheduler.py).
LIGHT_PRIORITIES = {
    "Quick Wins (High Impact-Low Effort)",
    "Fill-ins (Low Impact-Low Effort)",
}


def is_light_task(task: "Task") -> bool:
    return task.priority in LIGHT_PRIORITIES


def get_task_duration_minutes(task: "Task") -> int:
    return PRIORITY_DURATION_MINUTES.get(task.priority, DEFAULT_TASK_DURATION_MINUTES)


# Breathing room inserted between consecutive blocks (scheduler.py) --
# confirmed with the user 2026-08-03 after they noticed blocks were being
# packed back-to-back with no gap at all. Sized by effort, same grouping as
# LIGHT_PRIORITIES: a short breather after a light (Low Effort) task, a
# longer decompression break after a heavy (High Effort) one.
BREAK_MINUTES_LIGHT = 10
BREAK_MINUTES_HEAVY = 30


def get_task_break_minutes(task: "Task") -> int:
    return BREAK_MINUTES_LIGHT if is_light_task(task) else BREAK_MINUTES_HEAVY


class Task(NamedTuple):
    page_id: str
    name: str
    priority: Optional[str]
    start_date: date
    notes: str
    url: str
    specific_project: Optional[str] = None


_data_source_id_cache: Optional[str] = None


def _get_data_source_id(client: Client) -> str:
    # Permanently cached (not TTL-bound, unlike api/notion_cache.py's task
    # cache) -- a database's data_source_id is structural, it doesn't change
    # for the life of this database, so there's no staleness risk to guard
    # against, only a redundant network round trip to avoid.
    global _data_source_id_cache
    if _data_source_id_cache is None:
        db = client.databases.retrieve(database_id=NOTION_DATABASE_ID)
        _data_source_id_cache = db["data_sources"][0]["id"]
    return _data_source_id_cache


def _parse_date(date_prop: dict) -> Optional[date]:
    if not date_prop or not date_prop.get("date") or not date_prop["date"].get("start"):
        return None
    start = date_prop["date"]["start"]
    # Notion dates come back as either "YYYY-MM-DD" or a full ISO datetime.
    return datetime.fromisoformat(start.replace("Z", "+00:00")).date()


def _plain_text(rich_text_list: list) -> str:
    return "".join(t.get("plain_text", "") for t in rich_text_list)


def _first_multi_select(prop: dict) -> Optional[str]:
    """
    'Specific Project' is a multi_select -- used here only as a light
    questline tag (questlines.py), so a task with more than one value just
    uses the first. Returns None if the property is unset.
    """
    options = (prop or {}).get("multi_select") or []
    return options[0]["name"] if options else None


def _all_multi_select(prop: dict) -> List[str]:
    """Every value of a multi_select property, in Notion's own order --
    used by fetch_all_tasks() for the full tag extraction (unlike
    _first_multi_select, which is Priority/questline-generating logic
    predating tags and deliberately keeps only one value)."""
    options = (prop or {}).get("multi_select") or []
    return [o["name"] for o in options]


def _end_of_week(today: date) -> date:
    """
    The coming Sunday -- this project's last working day, see
    config.WORKING_WEEKDAYS -- or `today` itself if today already is
    Sunday. (Saturday joined WORKING_WEEKDAYS 2026-08-06 alongside the
    manual block grid, but Sunday remains the week's last day either way.)
    """
    return today + timedelta(days=(6 - today.weekday()) % 7)


def get_week_end(today: Optional[date] = None) -> date:
    """Public wrapper around _end_of_week -- used by app.py's block grid
    (block_grid.py) to compute the same day-tab range fetch_actionable_tasks()
    already fetches, without duplicating the "coming Sunday" logic."""
    return _end_of_week(today or date.today())


def fetch_actionable_tasks(today: Optional[date] = None) -> List[Task]:
    """
    Fetch and rank tasks whose start date ('Start on') has arrived, or
    arrives later this week -- start_date <= end of this week (see
    _end_of_week), not just start_date <= today (2026-08-03 same-day
    follow-up to the rule below): without a look-ahead, a task starting
    later in the week only ever became visible on the one day its own sync
    happened to run, so the calendar never showed more than "today" in
    advance. A task fetched ahead of its own start date still can't be
    *placed* on the calendar before that date arrives --
    scheduler.schedule_tasks() skips any candidate day earlier than the
    task's `start_date` -- so this only changes *when a task becomes
    visible for scheduling*, not which day it lands on.
    """
    today = today or date.today()
    fetch_through = _end_of_week(today)

    client = Client(auth=NOTION_TOKEN)
    data_source_id = _get_data_source_id(client)

    filter_obj = {
        "and": [
            {
                "or": [
                    {"property": "Completed", "select": {"equals": status}}
                    for status in ACTIONABLE_STATUSES
                ]
            },
            {"property": "Start on", "date": {"on_or_before": fetch_through.isoformat()}},
            {"property": "Priority", "select": {"is_not_empty": True}},
        ]
    }

    tasks: List[Task] = []
    cursor = None
    while True:
        kwargs = {"data_source_id": data_source_id, "filter": filter_obj, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        res = client.data_sources.query(**kwargs)
        for row in res["results"]:
            props = row["properties"]
            start_date = _parse_date(props.get("Start on", {}))
            if start_date is None:
                continue  # filter should already exclude these, but be defensive
            name_prop = props.get("Name", {}).get("title", [])
            priority_prop = props.get("Priority", {}).get("select")
            tasks.append(Task(
                page_id=row["id"],
                name=_plain_text(name_prop) or "(untitled)",
                priority=priority_prop["name"] if priority_prop else None,
                start_date=start_date,
                notes=_plain_text(props.get("Notes", {}).get("rich_text", [])),
                url=row.get("url", ""),
                specific_project=_first_multi_select(props.get("Specific Project")),
            ))
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    def sort_key(t: Task):
        # Pure Priority order, tie-broken by earliest start date within a
        # tier -- no "old start date jumps the queue" override (see the
        # module docstring's 2026-08-03 correction for why).
        rank = PRIORITY_ORDER.index(t.priority) if t.priority in PRIORITY_ORDER else len(PRIORITY_ORDER)
        return (rank, t.start_date)

    tasks.sort(key=sort_key)
    return tasks


class TaskWithStatus(NamedTuple):
    """Same shape as Task, plus the raw Notion status string -- a separate
    NamedTuple rather than adding a field to Task itself, since Task's
    exact field set is spread directly into TaskOut via `**t._asdict()`
    (api/routers/tasks.py) and callers of fetch_actionable_tasks() (the
    live app's only consumer of Task) don't need or expect a status field
    (fetch_actionable_tasks() already filters to a fixed status set).

    `tags` (second same-day follow-up) folds together two different Notion
    properties that both read as "tags" to the user: 'Block' (a single-
    select life-area category -- Research/Coursework/ASPARi operation/
    Teaching and Supervision/Personal and Service/Other, confirmed against
    the real database) and every value of 'Specific Project' (multi-select,
    ~48 options in the real database -- specific_project above only keeps
    the *first* one for questline-tracking compatibility, so anything
    beyond that would otherwise be silently dropped on migration)."""

    page_id: str
    name: str
    priority: Optional[str]
    start_date: Optional[date]
    notes: str
    url: str
    specific_project: Optional[str]
    status: Optional[str]
    tags: List[str]


def fetch_all_tasks() -> List[TaskWithStatus]:
    """
    Every non-archived task in the Notion database, regardless of status,
    Priority, or start date -- used once by migrate_notion_tasks.py for a
    full extraction into the native tasks table (procrastination_tool.
    tasks), NOT by the live app. fetch_actionable_tasks() deliberately
    excludes On-hold/Discarded/Completed tasks and anything without a
    Priority or a start date <= this week -- exactly wrong for "pull
    everything so nothing is silently left behind in Notion." A task with
    no Priority (the long-term-milestone case documented in this module's
    docstring) or no start date is still included here -- the caller
    decides how to handle those (see migrate_notion_tasks.py).

    No `Completed`/`Start on`/`Priority` filter at all -- only Notion's own
    archived/trashed state excludes a page, same as get_live_task_snapshot's
    "gone" check.
    """
    client = Client(auth=NOTION_TOKEN)
    data_source_id = _get_data_source_id(client)

    tasks: List[TaskWithStatus] = []
    cursor = None
    while True:
        kwargs = {"data_source_id": data_source_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        res = client.data_sources.query(**kwargs)
        for row in res["results"]:
            if row.get("archived") or row.get("in_trash"):
                continue
            props = row["properties"]
            name_prop = props.get("Name", {}).get("title", [])
            priority_prop = props.get("Priority", {}).get("select")
            completed_prop = props.get("Completed", {}).get("select")
            block_prop = props.get("Block", {}).get("select")
            tags = _all_multi_select(props.get("Specific Project"))
            if block_prop:
                tags = [block_prop["name"]] + tags
            tasks.append(TaskWithStatus(
                page_id=row["id"],
                name=_plain_text(name_prop) or "(untitled)",
                priority=priority_prop["name"] if priority_prop else None,
                start_date=_parse_date(props.get("Start on", {})),
                notes=_plain_text(props.get("Notes", {}).get("rich_text", [])),
                url=row.get("url", ""),
                specific_project=_first_multi_select(props.get("Specific Project")),
                status=completed_prop["name"] if completed_prop else None,
                tags=tags,
            ))
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    return tasks


class TaskSnapshot(NamedTuple):
    name: str
    priority: str
    start_date: date


def get_live_task_snapshot(page_id: str) -> Optional[TaskSnapshot]:
    """
    Fetch a single page's *current* (name, priority, start_date) directly by
    ID -- used by sync.py to reconcile an existing calendar block against
    what Notion says right now, not what it said when the block was
    created. Returns None if the page no longer qualifies as an
    actionable, scheduled-worthy task for any reason: it was deleted
    (retrieve raises), archived/trashed, its Completed status is no longer
    Not Started/In-Progress, or its Priority/Start-on has been cleared --
    every one of those means "this task's existing block, if any, should
    be removed," which is exactly how the caller uses a None result.

    Deliberately a single by-ID lookup rather than a bulk query: this
    workspace's newer data-sources API model means bulk queries only ever
    return non-archived, non-trashed, currently-matching pages -- there is
    no query that finds "a page that used to match but was deleted or
    edited out of matching." Checking each existing calendar block's tagged
    page_id directly is the only way to catch every case, not just a
    status-change subset of them.

    Only a genuine 404 (APIErrorCode.ObjectNotFound -- the page was
    permanently deleted, not just archived/trashed, which retrieve() can
    still fetch) is treated as "gone" here. Any other exception (rate limit,
    timeout, network blip) is a transient failure to *check*, not evidence
    the task is gone, and is left to propagate -- the caller
    (sync._reconcile_calendar_with_notion) is responsible for deciding what
    "couldn't verify this one" means for its own loop, rather than this
    function silently treating "couldn't check" the same as "confirmed
    gone." Swallowing every exception into None here previously meant a
    transient Notion API error during reconciliation could delete a live
    task's calendar block -- a real, if rare, silent-data-loss bug.
    """
    client = Client(auth=NOTION_TOKEN)
    try:
        page = client.pages.retrieve(page_id=page_id)
    except APIResponseError as e:
        if e.code == APIErrorCode.ObjectNotFound:
            return None  # permanently deleted
        raise

    if page.get("archived") or page.get("in_trash"):
        return None

    props = page["properties"]
    completed_prop = props.get("Completed", {}).get("select")
    completed = completed_prop["name"] if completed_prop else None
    if completed not in ACTIONABLE_STATUSES:
        return None

    priority_prop = props.get("Priority", {}).get("select")
    priority = priority_prop["name"] if priority_prop else None
    if priority is None:
        return None

    start_date = _parse_date(props.get("Start on", {}))
    if start_date is None:
        return None

    name = _plain_text(props.get("Name", {}).get("title", [])) or "(untitled)"
    return TaskSnapshot(name=name, priority=priority, start_date=start_date)


def mark_task_completed(page_id: str) -> None:
    """
    Sets the task's Completed status to 'Completed' in Notion -- this
    project's first WRITE to Notion (every other call in this module is
    read-only). Used by the manual block grid's "Done" button (app.py).

    Requires the integration token (NOTION_TOKEN) to have "Update content"
    capability enabled at notion.so/my-integrations -- read-only capability
    was sufficient for everything before this. A missing capability
    surfaces as a 403 from the Notion API and is left to raise here rather
    than being swallowed, so a misconfigured token fails loudly instead of
    silently no-opping.
    """
    client = Client(auth=NOTION_TOKEN)
    client.pages.update(page_id=page_id, properties={"Completed": {"select": {"name": "Completed"}}})
