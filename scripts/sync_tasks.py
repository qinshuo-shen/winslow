#!/usr/bin/env python3
"""
LaunchAgent-driven daily wrapper around procrastination_tool.sync.run_sync()
-- handles file logging, exit codes, and the completion notification. The
actual Notion->Calendar sync logic lives in sync.py (shared with app.py's
manual sync button), not here.

**LaunchAgent unloaded 2026-08-07**: this script's `run_sync()` call includes
scheduler.schedule_tasks() (the old automatic first-fit placer), which was
found to still be firing daily/on-login and auto-creating calendar blocks in
silent competition with the new manual drag-and-drop grid (React dashboard).
The installed copy at `~/Library/LaunchAgents/com.qinshuoshen.procrastination-tool.sync.plist`
has been `launchctl unload`ed and removed; the repo's own source copy at
`launchd/com.qinshuoshen.procrastination-tool.sync.plist` is untouched, so
re-enabling later is just re-copying it back and bootstrapping (see
README.md's "Reloading the sync agent" section). This script itself is left
on disk, working, and runnable manually -- but running it by hand will still
auto-schedule blocks via scheduler.py, same as before. Use the dashboard's
"Refresh (Notion + Calendar)" button instead for reconciliation-only cleanup
(it calls sync._reconcile_calendar_with_notion() directly, not this script).
"""
import sys
from datetime import datetime

from procrastination_tool import notify, sync
from procrastination_tool.config import LOG_DIR


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_DIR / "sync_tasks.log", "a") as f:
        f.write(line + "\n")


def main() -> int:
    log("=== sync_tasks starting ===")

    try:
        result = sync.run_sync(log_fn=log)
    except Exception as e:
        log(f"FAIL: {e!r}")
        return 1

    if result.unscheduled:
        log(f"WARNING: unscheduled tasks: {[t.name for t in result.unscheduled]}")

    try:
        summary = f"{len(result.created)} task block(s) scheduled" + (
            f", {len(result.unscheduled)} unscheduled" if result.unscheduled else ""
        ) + (
            f", {result.removed_count} completed task block(s) removed" if result.removed_count else ""
        )
        notify.send_notification("Procrastination Tool — Sync", summary)
    except Exception as e:
        log(f"WARNING: notify raised {e!r} (non-fatal)")

    log(f"=== sync_tasks PASSED: {len(result.created)} created, "
        f"{len(result.already_blocked)} already blocked, {len(result.unscheduled)} unscheduled, "
        f"{result.removed_count} removed (completed/discarded) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
