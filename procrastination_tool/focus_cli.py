"""
`focus` CLI entry point (installed via pyproject.toml's [project.scripts]).

    focus start [--duration 25] [--task "Draft review"] [--pick]
    focus history [--limit 10]

2026-08-11, third same-day follow-up: the `rest` subcommand (RPG character
sheet / bonfire stat leveling) is removed -- the Runes reward system is no
longer part of the live app (see focus_timer.py's finalize_session()).
character.py/bloodstain.py are left on disk, unused, same convention as
this project's other retired modules.
"""
import argparse
import os
import sys

from . import auth, device_lock, focus_timer, notion_tasks
from .config import FOCUS_SESSION_MINUTES


def _pick_task(args: argparse.Namespace):
    """Interactive picker for a live actionable Notion task -- returns a
    notion_tasks.Task or None if the user cancels/there's nothing to pick."""
    tasks = notion_tasks.fetch_actionable_tasks()
    if not tasks:
        print("No actionable Notion tasks found -- falling back to --task/no label.")
        return None
    print("Actionable tasks:")
    for i, t in enumerate(tasks):
        print(f"  [{i}] {t.name}  ({t.priority}, starts {t.start_date})")
    choice = input(f"Pick a task [0-{len(tasks) - 1}, blank to skip]: ").strip()
    if not choice:
        return None
    try:
        return tasks[int(choice)]
    except (ValueError, IndexError):
        print("Invalid choice -- falling back to --task/no label.")
        return None


def _cmd_start(args: argparse.Namespace) -> int:
    task_label = args.task
    priority = None
    specific_project = None

    if args.pick:
        picked = _pick_task(args)
        if picked is not None:
            task_label = picked.name
            priority = picked.priority
            specific_project = picked.specific_project

    focus_timer.run_focus_session(
        duration_minutes=args.duration, task_label=task_label,
        priority=priority, specific_project=specific_project,
    )
    return 0


def _status_label(s: focus_timer.SessionRow) -> str:
    if s.outcome == focus_timer.OUTCOME_FAILED_PAUSE_TIMEOUT:
        return "failed"
    return "done" if s.completed else "early"


def _cmd_history(args: argparse.Namespace) -> int:
    # Multi-user follow-up: the CLI always runs as the owner (the first
    # account created) -- see focus_timer.run_focus_session()'s docstring
    # for why, same reasoning applies here.
    owner = auth.get_owner_user()
    if owner is None:
        print("No account exists yet -- run scripts/create_user.py first.", file=sys.stderr)
        return 1
    sessions = focus_timer.get_recent_sessions(owner.id, limit=args.limit)
    if not sessions:
        print("No focus sessions logged yet.")
        return 0
    for s in sessions:
        status = _status_label(s)
        label = f" [{s.task_label}]" if s.task_label else ""
        print(f"{s.start_time.strftime('%Y-%m-%d %H:%M')}  {s.actual_minutes:5.1f}min  {status:6s}{label}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="focus", description="Self-reported Pomodoro-style focus timer.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser(
        "start", help="Start a focus session (blocks until done; Ctrl-C to stop early, 'p'/'r' to pause/resume).")
    start_parser.add_argument("--duration", type=float, default=FOCUS_SESSION_MINUTES,
                               help=f"Session length in minutes (default: {FOCUS_SESSION_MINUTES:g}).")
    start_parser.add_argument("--task", type=str, default=None, help="Optional label for what you're working on.")
    start_parser.add_argument("--pick", action="store_true",
                               help="Pick a live actionable Notion task instead of a free-text --task label.")
    start_parser.set_defaults(func=_cmd_start)

    history_parser = subparsers.add_parser("history", help="Show recent focus sessions.")
    history_parser.add_argument("--limit", type=int, default=10, help="Number of recent sessions to show.")
    history_parser.set_defaults(func=_cmd_history)

    args = parser.parse_args()

    # Same cross-device write-safety guard the web server uses (see
    # procrastination_tool/device_lock.py and api/main.py's lifespan) --
    # this CLI touches data/sessions.db directly too, independent of
    # whether the web server is also installed on this machine.
    try:
        device_lock.acquire(force=os.environ.get("PROCRASTINATION_TOOL_FORCE_UNLOCK") == "1")
    except device_lock.DeviceLockError as e:
        print(f"Refusing to start: {e}", file=sys.stderr)
        return 1

    try:
        return args.func(args)
    finally:
        device_lock.release()


if __name__ == "__main__":
    sys.exit(main())
