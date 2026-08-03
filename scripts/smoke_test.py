#!/usr/bin/env python3
"""
Phase 0 de-risking test: proves the riskiest assumption in the whole
project -- that Calendar Automation + Notification permissions, once
granted, keep working from a *non-interactive* context (a launchd
LaunchAgent), not just when run manually from an interactive Terminal.

Run this manually first (from Terminal, not via Claude Code) to trigger
and approve the permission dialogs. Then load/kickstart the LaunchAgent
and check logs/smoke_test.log to confirm it succeeds there too, with no
prompt appearing (because it was already granted).

Exit code 0 = all checks passed. Non-zero = see stderr/log for which step
failed.
"""
import sys
from datetime import datetime, timedelta

from procrastination_tool import calendar_bridge, notify, notion_client_wrapper
from procrastination_tool.config import LOG_DIR


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_DIR / "smoke_test.log", "a") as f:
        f.write(line + "\n")


def main() -> int:
    log("=== smoke test starting ===")

    if notion_client_wrapper.is_configured():
        try:
            title = notion_client_wrapper.check_connection()
            log(f"OK: Notion connected, database title = {title!r}")
        except Exception as e:
            log(f"FAIL: Notion check raised {e!r}")
            return 1
    else:
        log("SKIP: Notion not configured yet (NOTION_TOKEN/NOTION_DATABASE_ID unset in .env) -- "
            "fine for now, but this must pass before Phase 0 is fully done per the plan.")

    try:
        calendar_bridge.ensure_calendar()
        log("OK: 'Focus Blocks' calendar exists (or was created)")
    except Exception as e:
        log(f"FAIL: ensure_calendar raised {e!r}")
        return 1

    start = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = start + timedelta(minutes=15)
    test_title = f"[smoke-test] {start.isoformat()}"

    try:
        uid = calendar_bridge.create_event(test_title, start, end, notes="Phase 0 smoke test event")
        log(f"OK: created test event, uid={uid}")
    except Exception as e:
        log(f"FAIL: create_event raised {e!r}")
        return 1

    try:
        todays_events = calendar_bridge.list_events(start)
        found = any(ev.uid == uid for ev in todays_events)
        if found:
            log(f"OK: test event found via list_events ({len(todays_events)} event(s) today)")
        else:
            log(f"FAIL: test event uid {uid} not found among {len(todays_events)} listed event(s)")
            return 1
    except Exception as e:
        log(f"FAIL: list_events raised {e!r}")
        return 1

    try:
        deleted = calendar_bridge.delete_event_by_uid(uid)
        log(f"OK: delete_event_by_uid returned {deleted}")
    except Exception as e:
        log(f"FAIL: delete_event_by_uid raised {e!r}")
        return 1

    try:
        notify.send_notification(
            "Procrastination Tool — Phase 0",
            "Smoke test passed. If you can see this, Notification permission is granted.",
        )
        log("OK: notification sent (verify VISUALLY that it appeared on screen -- exit code alone doesn't prove it)")
    except Exception as e:
        log(f"FAIL: send_notification raised {e!r}")
        return 1

    log("=== smoke test PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
