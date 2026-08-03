"""
`focus` CLI entry point (installed via pyproject.toml's [project.scripts]).

    focus start [--duration 25] [--task "Draft review"]
    focus history [--limit 10]
"""
import argparse
import sys

from . import focus_timer
from .config import FOCUS_SESSION_MINUTES


def _cmd_start(args: argparse.Namespace) -> int:
    focus_timer.run_focus_session(duration_minutes=args.duration, task_label=args.task)
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
        reward = f" -> {s.wheel_result}" if s.wheel_result else ""
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
    start_parser.set_defaults(func=_cmd_start)

    history_parser = subparsers.add_parser("history", help="Show recent focus sessions.")
    history_parser.add_argument("--limit", type=int, default=10, help="Number of recent sessions to show.")
    history_parser.set_defaults(func=_cmd_history)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
