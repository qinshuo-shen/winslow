"""
Desktop notification wrapper. macOS backend via osascript today; dispatched
by sys.platform so a Windows/Linux backend (e.g. a cross-platform library
like `desktop-notifier`) can be added later without touching call sites --
the productization roadmap commits to cross-platform from the start, but
only the macOS backend is implemented/testable right now.

Known gotcha (flagged in the project plan): `osascript -e 'display
notification'` can exit 0 while silently dropping the notification if
Notification permission for the requesting process hasn't been granted in
System Settings > Privacy & Security > Notifications. Don't trust the exit
code alone -- the Phase 0 smoke test verifies this visually.
"""
import subprocess
import sys


def _escape_as_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _send_macos(title: str, message: str, subtitle: str = "") -> None:
    title_esc = _escape_as_string(title)
    message_esc = _escape_as_string(message)
    subtitle_esc = _escape_as_string(subtitle)
    script = f'display notification "{message_esc}" with title "{title_esc}"'
    if subtitle:
        script += f' subtitle "{subtitle_esc}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)


def send_notification(title: str, message: str, subtitle: str = "") -> None:
    if sys.platform == "darwin":
        _send_macos(title, message, subtitle)
    else:
        # No Windows/Linux backend yet -- see module docstring. Fail
        # silently rather than crash the caller (a missed nudge shouldn't
        # take down the scheduler tick loop).
        pass


def send_actionable_notification(task_name: str, subtitle: str = "") -> None:
    """The proactive-scheduler nudge -- pre-loaded with the one task to
    start, framed supportively (never guilt/urgency language, per the
    redesign's UI direction). No OS-level click-to-start action exists via
    osascript (display notification has no button/action support at all);
    the real one-tap Start/Swap surface is the app's own Now view, which
    the notification's presence is meant to draw the user toward -- see the
    plan's notification-design note."""
    send_notification(
        title=task_name,
        message="Ready when you are.",
        subtitle=subtitle,
    )
