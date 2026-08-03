"""
macOS notification wrapper via osascript.

Known gotcha (flagged in the project plan): `osascript -e 'display
notification'` can exit 0 while silently dropping the notification if
Notification permission for the requesting process hasn't been granted in
System Settings > Privacy & Security > Notifications. Don't trust the exit
code alone -- the Phase 0 smoke test verifies this visually.
"""
import subprocess


def _escape_as_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def send_notification(title: str, message: str, subtitle: str = "") -> None:
    title_esc = _escape_as_string(title)
    message_esc = _escape_as_string(message)
    subtitle_esc = _escape_as_string(subtitle)
    script = f'display notification "{message_esc}" with title "{title_esc}"'
    if subtitle:
        script += f' subtitle "{subtitle_esc}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
