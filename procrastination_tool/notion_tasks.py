"""
Query and rank actionable tasks from the Notion tasks database.

Schema (as of 2026-08-02, confirmed against the real database -- not
assumed): 'Name' (title), 'Priority' (select, Eisenhower-style categories,
not a simple rank), 'Block' (select, life-area tag), 'Specific Project'
(multi_select), 'Date' (date), 'Completed' (select: Not Started/In-Progress/
On hold/Completed/Discarded), 'Notes' (rich_text).

**Correction, 2026-08-03**: 'Date' is the task's *start* date, not a
deadline -- confirmed with the user after the original "overdue tasks
always jump the queue" ranking turned out to be flooding today's schedule,
since most of the backlog's start dates were already in the past and all
of it was getting treated as maximally urgent. There is no separate
deadline property in this database. The `Task.due`/`TaskSnapshot.due`
field names are kept as-is (not renamed) to avoid a wide, purely-cosmetic
rename across this module, scheduler.py, sync.py, and calendar_bridge.py's
notes tag -- but the value they hold is a start date; nothing here treats
it as a deadline.

This workspace is on Notion's newer "data sources" API model -- a database
no longer carries `properties` directly; you retrieve its data_sources[0]
id first, then query/retrieve *that*. See config.get_data_source_id().

Design decisions made explicitly with the user, not guessed:
- Only 'Not Started' and 'In-Progress' count as actionable (On hold,
  Discarded, Completed all excluded).
- **(2026-08-02)** Only tasks with a Date set are considered at all --
  undated tasks are left out of auto-scheduling entirely (add a Date in
  Notion if you want something scheduled).
- **(2026-08-03, replacing the original 2026-08-02 rule)** A task is only
  actionable once its start date has arrived: `Date <= today`. Ranking is
  pure Priority order (see PRIORITY_ORDER) tie-broken by earliest start
  date within the same tier. There is no more "jump the queue" override
  for an old start date; a task that's been sitting unstarted for a while
  doesn't outrank a higher-Priority task that just became eligible today.
- **(2026-08-03, same-day follow-up)** Added a *rest-of-week* look-ahead:
  the fetch filter is `Date <= end of this week` (through Sunday, this
  project's last working day -- see config.WORKING_WEEKDAYS) instead of
  `Date <= today`, so Tuesday-Friday tasks show up on the calendar today
  instead of trickling in one sync per day. A task still can't actually be
  *placed* before its own start date -- scheduler.schedule_tasks() skips
  any candidate day earlier than the task's `due` (start date) when
  choosing a slot -- so this only changes *when a task becomes visible for
  scheduling*, not the day it lands on.
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
- **Tasks with no Priority set are excluded from auto-scheduling entirely**
  (2026-08-02 follow-up, after the first live run): the user uses "No
  Priority" for long-term projects (e.g. an ongoing research project, a
  personal side project) that aren't meant to be chunked into a single
  short daily block. Give a
  task a Priority in Notion once it's actually actionable in the near
  term, and it'll start showing up here.
- **Duration is derived from Priority, not a flat default** (same
  follow-up, after the first live run's 1-hour-for-everything blocks
  turned out unrealistic): see PRIORITY_DURATION_MINUTES below.
"""
from datetime import date, datetime, timedelta
from typing import List, NamedTuple, Optional

from notion_client import Client

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
    due: date
    notes: str
    url: str


def _get_data_source_id(client: Client) -> str:
    db = client.databases.retrieve(database_id=NOTION_DATABASE_ID)
    return db["data_sources"][0]["id"]


def _parse_date(date_prop: dict) -> Optional[date]:
    if not date_prop or not date_prop.get("date") or not date_prop["date"].get("start"):
        return None
    start = date_prop["date"]["start"]
    # Notion dates come back as either "YYYY-MM-DD" or a full ISO datetime.
    return datetime.fromisoformat(start.replace("Z", "+00:00")).date()


def _plain_text(rich_text_list: list) -> str:
    return "".join(t.get("plain_text", "") for t in rich_text_list)


def _end_of_week(today: date) -> date:
    """
    The coming Sunday -- this project's last working day, see
    config.WORKING_WEEKDAYS -- or `today` itself if today already is
    Sunday. Saturday is excluded from WORKING_WEEKDAYS entirely, so "end
    of week" deliberately means Sunday, not Saturday.
    """
    return today + timedelta(days=(6 - today.weekday()) % 7)


def fetch_actionable_tasks(today: Optional[date] = None) -> List[Task]:
    """
    Fetch and rank tasks whose start date (Date) has arrived, or arrives
    later this week -- Date <= end of this week (see _end_of_week), not
    just Date <= today (2026-08-03 same-day follow-up to the rule below):
    without a look-ahead, a task due later in the week only ever became
    visible on the one day its own sync happened to run, so the calendar
    never showed more than "today" in advance. A task fetched ahead of its
    own start date still can't be *placed* on the calendar before that
    date arrives -- scheduler.schedule_tasks() skips any candidate day
    earlier than the task's `due` -- so this only changes *when a task
    becomes visible for scheduling*, not which day it lands on.
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
            {"property": "Date", "date": {"on_or_before": fetch_through.isoformat()}},
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
            due = _parse_date(props.get("Date", {}))
            if due is None:
                continue  # filter should already exclude these, but be defensive
            name_prop = props.get("Name", {}).get("title", [])
            priority_prop = props.get("Priority", {}).get("select")
            tasks.append(Task(
                page_id=row["id"],
                name=_plain_text(name_prop) or "(untitled)",
                priority=priority_prop["name"] if priority_prop else None,
                due=due,
                notes=_plain_text(props.get("Notes", {}).get("rich_text", [])),
                url=row.get("url", ""),
            ))
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    def sort_key(t: Task):
        # Pure Priority order, tie-broken by earliest start date within a
        # tier -- no "old start date jumps the queue" override (see the
        # module docstring's 2026-08-03 correction for why).
        rank = PRIORITY_ORDER.index(t.priority) if t.priority in PRIORITY_ORDER else len(PRIORITY_ORDER)
        return (rank, t.due)

    tasks.sort(key=sort_key)
    return tasks


class TaskSnapshot(NamedTuple):
    name: str
    priority: str
    due: date


def get_live_task_snapshot(page_id: str) -> Optional[TaskSnapshot]:
    """
    Fetch a single page's *current* (name, priority, due) directly by ID --
    used by sync.py to reconcile an existing calendar block against
    what Notion says right now, not what it said when the block was
    created. Returns None if the page no longer qualifies as an
    actionable, scheduled-worthy task for any reason: it was deleted
    (retrieve raises), archived/trashed, its Completed status is no longer
    Not Started/In-Progress, or its Priority/Date has been cleared --
    every one of those means "this task's existing block, if any, should
    be removed," which is exactly how the caller uses a None result.

    Deliberately a single by-ID lookup rather than a bulk query: this
    workspace's newer data-sources API model means bulk queries only ever
    return non-archived, non-trashed, currently-matching pages -- there is
    no query that finds "a page that used to match but was deleted or
    edited out of matching." Checking each existing calendar block's tagged
    page_id directly is the only way to catch every case, not just a
    status-change subset of them.
    """
    client = Client(auth=NOTION_TOKEN)
    try:
        page = client.pages.retrieve(page_id=page_id)
    except Exception:
        return None  # deleted (permanently) or otherwise unreachable

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

    due = _parse_date(props.get("Date", {}))
    if due is None:
        return None

    name = _plain_text(props.get("Name", {}).get("title", [])) or "(untitled)"
    return TaskSnapshot(name=name, priority=priority, due=due)
