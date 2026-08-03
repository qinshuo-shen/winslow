#!/usr/bin/env python3
"""
LaunchAgent-driven daily wrapper around procrastination_tool.sync.run_sync()
-- handles file logging, exit codes, and the completion notification. The
actual Notion->Calendar sync logic lives in sync.py (shared with app.py's
manual sync button), not here.
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
