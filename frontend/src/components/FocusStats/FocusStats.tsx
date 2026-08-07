import { useEffect, useState } from "react";
import { apiGet, ApiError } from "../../api/client";
import type { SessionOut, StatsOut } from "../../api/types";
import { DailyBarChart } from "./DailyBarChart";
import { SessionHistoryList } from "./SessionHistoryList";
import "./FocusStats.css";

// Mirrors app.py's "Focus sessions" section:
//   - empty state keyed off `sessions` (GET /api/sessions/recent?limit=50,
//     the same all-time-recent fetch app.py uses), NOT off the 7-day window
//     -- a user with sessions older than 7 days still sees the metrics row
//     (zeros/em-dash) and their session history, exactly like app.py.
//   - the three metrics + daily chart come from GET /api/sessions/stats?days=7,
//     which mirrors app.py's inline week_sessions/completed_week computation.
//   - "Recent sessions" always fetches 50 but only displays the first 10
//     (app.py: `for s in sessions[:10]`), so the same fetch can later back
//     a "show more" without a second endpoint.

interface FocusStatsProps {
  // Bumped by App.tsx whenever FocusTimerWidget reports a session ended,
  // so this refetches without adding its own polling -- see App.tsx's
  // 2026-08-07 comment for the full rationale.
  refreshKey?: number;
}

export function FocusStats({ refreshKey }: FocusStatsProps) {
  const [stats, setStats] = useState<StatsOut | null>(null);
  const [sessions, setSessions] = useState<SessionOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      apiGet<StatsOut>("/sessions/stats?days=7"),
      apiGet<SessionOut[]>("/sessions/recent?limit=50"),
    ])
      .then(([statsData, sessionsData]) => {
        if (cancelled) return;
        setStats(statsData);
        setSessions(sessionsData);
      })
      .catch((e: ApiError) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (error) {
    return (
      <section className="focus-stats">
        <h2>Focus sessions</h2>
        <p className="focus-stats__error">{error}</p>
      </section>
    );
  }

  if (stats === null || sessions === null) {
    return (
      <section className="focus-stats">
        <h2>Focus sessions</h2>
        <p className="focus-stats__loading">Loading…</p>
      </section>
    );
  }

  if (sessions.length === 0) {
    return (
      <section className="focus-stats">
        <h2>Focus sessions</h2>
        <p className="focus-stats__empty">
          No focus sessions logged yet — run <code>focus start</code> from Terminal.
        </p>
      </section>
    );
  }

  const completionRateLabel =
    stats.completion_rate === null ? "—" : `${Math.round(stats.completion_rate * 100)}%`;
  const focusedTimeLabel = `${stats.focused_minutes.toFixed(0)} min (${(
    stats.focused_minutes / 60
  ).toFixed(1)} h)`;

  return (
    <section className="focus-stats">
      <h2>Focus sessions</h2>

      <div className="focus-stats__metrics">
        <div className="focus-stats__metric">
          <span className="focus-stats__metric-label">Sessions (7d)</span>
          <span className="focus-stats__metric-value">{stats.sessions}</span>
        </div>
        <div className="focus-stats__metric">
          <span className="focus-stats__metric-label">Completion rate (7d)</span>
          <span className="focus-stats__metric-value">{completionRateLabel}</span>
        </div>
        <div className="focus-stats__metric">
          <span className="focus-stats__metric-label">Focused time (7d)</span>
          <span className="focus-stats__metric-value">{focusedTimeLabel}</span>
        </div>
      </div>

      <DailyBarChart dailyMinutes={stats.daily_minutes} />

      <SessionHistoryList sessions={sessions.slice(0, 10)} />
    </section>
  );
}

export default FocusStats;
