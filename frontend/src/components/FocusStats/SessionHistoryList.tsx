import type { SessionOut } from "../../api/types";
import "./SessionHistoryList.css";

// Mirrors app.py's "Recent sessions" loop:
//   status = ⏰ if outcome == failed_pause_timeout, else ✅ if completed, else ⏹️
//   f"{status} {start:%Y-%m-%d %H:%M}  ({actual_minutes:.0f}min){label}"
// where label = " — {task_label}" if task_label.
//
// 2026-08-11, third same-day follow-up: no longer shows a Runes reward
// suffix (even for historical sessions that did earn Runes under the old
// system) -- the RPG reward system is removed from the live app.

const OUTCOME_FAILED_PAUSE_TIMEOUT = "failed_pause_timeout";

function statusIcon(s: SessionOut): string {
  if (s.outcome === OUTCOME_FAILED_PAUSE_TIMEOUT) return "⏰";
  if (s.completed) return "✅";
  return "⏹️";
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function formatSessionLine(s: SessionOut): string {
  const start = new Date(s.start_time);
  const dateLabel = `${start.getFullYear()}-${pad2(start.getMonth() + 1)}-${pad2(
    start.getDate(),
  )} ${pad2(start.getHours())}:${pad2(start.getMinutes())}`;
  const label = s.task_label ? ` — ${s.task_label}` : "";
  return `${dateLabel}  (${s.actual_minutes.toFixed(0)}min)${label}`;
}

interface SessionHistoryListProps {
  sessions: SessionOut[];
}

export function SessionHistoryList({ sessions }: SessionHistoryListProps) {
  return (
    <div className="session-history">
      <h3>Recent sessions</h3>
      <ul className="session-history__list">
        {sessions.map((s) => (
          <li key={s.id}>
            <span className="session-history__icon" aria-hidden="true">
              {statusIcon(s)}
            </span>{" "}
            {formatSessionLine(s)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default SessionHistoryList;
