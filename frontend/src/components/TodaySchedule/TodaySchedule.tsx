import { useEffect, useState } from "react";
import { apiGet, ApiError } from "../../api/client";
import type { CalendarEventOut } from "../../api/types";
import "./TodaySchedule.css";

// Mirrors app.py's "Today's schedule" section exactly: GET /api/calendar/today
// wraps calendar_bridge.list_events(datetime.now()) sorted by start (server
// does the sort -- see api/routers/calendar.py), rendered as
// "HH:MM–HH:MM  Summary" lines, or the same empty-state / error copy as
// app.py's try/except around the underlying AppleScript call.

function formatHHMM(iso: string): string {
  // Manual HH:MM formatting (not toLocaleTimeString) so this matches
  // Python's %H:%M exactly regardless of browser locale/12h settings.
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function TodaySchedule() {
  const [events, setEvents] = useState<CalendarEventOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<CalendarEventOut[]>("/calendar/today")
      .then((data) => {
        if (!cancelled) setEvents(data);
      })
      .catch((e: ApiError) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="today-schedule">
      <h2>Today&apos;s schedule</h2>

      {error && <p className="today-schedule__error">{error}</p>}

      {!error && events === null && (
        <p className="today-schedule__loading">Loading…</p>
      )}

      {!error && events !== null && events.length === 0 && (
        <p className="today-schedule__empty">No blocks scheduled for today yet.</p>
      )}

      {!error && events !== null && events.length > 0 && (
        <ul className="today-schedule__list">
          {events.map((ev) => (
            <li key={ev.uid}>
              <strong>
                {formatHHMM(ev.start)}–{formatHHMM(ev.end)}
              </strong>{" "}
              {ev.summary}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default TodaySchedule;
