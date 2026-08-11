"""
One-time extraction: pull every task out of the Notion database and insert
it into the native `tasks` table (procrastination_tool.tasks), then the
live app never needs to touch Notion again (see api/main.py, which stops
registering the legacy Notion-backed /api/tasks router once this has run).

Run manually, once, from the repo root:

    python -m procrastination_tool.migrate_notion_tasks

Safe to re-run (e.g. after fixing a config problem partway through): it
does not delete or de-duplicate against existing native tasks, so running
it twice will import everything twice. Check the printed summary against
the live Notion database before treating the migration as done, and don't
re-run it once you're satisfied everything came across.

Mapping decisions:
- Notion `Completed` status -> native status: "Not Started"->not_started,
  "In-Progress"->in_progress, "On hold"->on_hold, "Completed"->completed.
  "Discarded" and anything unrecognized are skipped (they're not real
  backlog items). Unset status is treated as not_started.
- Notion `Priority` (quadrant) is carried over as-is when set. A task with
  no Priority (the long-term-milestone case documented in notion_tasks.py
  -- deliberately excluded from the old actionable-tasks dashboard) is
  still imported here, not dropped -- "completely extract all info" means
  exactly that. It's bucketed into the lowest-effort quadrant (Fill-ins)
  with a note appended flagging that it had no Priority in Notion, so it
  doesn't just silently show up in a low-effort bucket with no explanation.
- `Notes` and `Specific Project` are carried over verbatim. The task's
  original Notion `Start on` date (if any) and URL are appended to the
  notes as a small provenance footer, since the native schema has no
  start-date concept at all (see tasks.py).
- Tags (second same-day follow-up): 'Block' + every 'Specific Project'
  value are imported as native tags (see notion_tasks.TaskWithStatus's
  docstring) -- richer than `specific_project` above, which only keeps the
  first Specific Project value for questline-tracking compatibility.
"""
from . import tasks
from .notion_tasks import PRIORITY_ORDER, TaskWithStatus, fetch_all_tasks

_STATUS_MAP = {
    "Not Started": tasks.STATUS_NOT_STARTED,
    "In-Progress": tasks.STATUS_IN_PROGRESS,
    "On hold": tasks.STATUS_ON_HOLD,
    "Completed": tasks.STATUS_COMPLETED,
}
_SKIP_STATUSES = {"Discarded"}

_NO_PRIORITY_QUADRANT = PRIORITY_ORDER[-1]  # "Fill-ins (Low Impact-Low Effort)"


def _build_notes(t: TaskWithStatus, no_priority: bool) -> str:
    notes = t.notes
    if no_priority:
        notes = (notes + "\n\n" if notes else "") + "(no priority set in Notion)"
    footer_bits = []
    if t.start_date:
        footer_bits.append(f"Notion start date: {t.start_date.isoformat()}")
    if t.url:
        footer_bits.append(f"Notion: {t.url}")
    if footer_bits:
        notes = (notes + "\n\n" if notes else "") + "\n".join(footer_bits)
    return notes


def migrate() -> None:
    notion_tasks = fetch_all_tasks()

    imported = 0
    skipped_discarded = 0
    skipped_unrecognized_status = 0
    no_priority_count = 0

    for t in notion_tasks:
        raw_status = t.status or "Not Started"
        if raw_status in _SKIP_STATUSES:
            skipped_discarded += 1
            continue
        status = _STATUS_MAP.get(raw_status)
        if status is None:
            print(f"  skipping {t.name!r}: unrecognized Notion status {raw_status!r}")
            skipped_unrecognized_status += 1
            continue

        no_priority = t.priority is None or t.priority not in PRIORITY_ORDER
        if no_priority:
            no_priority_count += 1
        priority = t.priority if not no_priority else _NO_PRIORITY_QUADRANT

        tasks.add_task(
            name=t.name,
            priority=priority,
            notes=_build_notes(t, no_priority),
            specific_project=t.specific_project,
            status=status,
            tags=t.tags,
        )
        imported += 1

    print(f"Notion tasks found:        {len(notion_tasks)}")
    print(f"Imported:                  {imported}")
    print(f"  (no Priority in Notion): {no_priority_count}")
    print(f"Skipped (Discarded):       {skipped_discarded}")
    print(f"Skipped (unknown status):  {skipped_unrecognized_status}")
    print()
    print("Cross-check this against the live Notion database before "
          "treating the migration as done.")


if __name__ == "__main__":
    migrate()
