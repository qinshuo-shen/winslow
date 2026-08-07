"""
`focus` CLI entry point (installed via pyproject.toml's [project.scripts]).

    focus start [--duration 25] [--task "Draft review"] [--pick]
    focus history [--limit 10]
    focus rest [--stat Intelligence]
"""
import argparse
import sys

from . import character, focus_timer, notion_tasks
from .bloodstain import get_active_bloodstain
from .config import CHARACTER_STATS, FOCUS_SESSION_MINUTES, stat_level_cost


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


def _cmd_rest(args: argparse.Namespace) -> int:
    if args.stat:
        try:
            new_level, runes_spent = character.spend_runes_on_stat(args.stat)
        except ValueError as e:
            print(f"Can't rest: {e}")
            return 1
        print(f"Rested at the bonfire -- {args.stat} is now level {new_level} "
              f"({runes_spent} Runes spent).")

    c = character.get_character()
    print(f"\nCharacter sheet -- Level {c.level}, {c.runes} Runes")
    for stat_name in CHARACTER_STATS:
        level = c.stats.get(stat_name, 0)
        cost = stat_level_cost(level)
        print(f"  {stat_name:12s} lvl {level:3d}  (next level: {cost} Runes)")

    stain = get_active_bloodstain()
    if stain:
        print(f"\n⚠ Active bloodstain: {stain.runes} Runes waiting to be recovered "
              "by your next completed session.")
    return 0


def _status_label(s: focus_timer.SessionRow) -> str:
    if s.outcome == focus_timer.OUTCOME_FAILED_PAUSE_TIMEOUT:
        return "failed"
    return "done" if s.completed else "early"


def _cmd_history(args: argparse.Namespace) -> int:
    sessions = focus_timer.get_recent_sessions(limit=args.limit)
    if not sessions:
        print("No focus sessions logged yet.")
        return 0
    for s in sessions:
        status = _status_label(s)
        label = f" [{s.task_label}]" if s.task_label else ""
        reward = f" -> +{s.runes_awarded} Runes" if s.runes_awarded else ""
        print(f"{s.start_time.strftime('%Y-%m-%d %H:%M')}  {s.actual_minutes:5.1f}min  {status:6s}{label}{reward}")
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

    rest_parser = subparsers.add_parser(
        "rest", help="View your character sheet, and optionally spend Runes to level a stat (bonfire leveling).")
    rest_parser.add_argument("--stat", type=str, default=None, choices=CHARACTER_STATS,
                              help="Spend Runes to level this stat by one.")
    rest_parser.set_defaults(func=_cmd_rest)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
