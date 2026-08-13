import { useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "../../api/client";
import type { WeeklyRetroOut } from "../../api/types";
import "./Retro.css";

// Weekly retro + velocity trend (Scrum-lite feature set). Sibling to
// Evaluation.tsx, not a modification of it -- daily and weekly are
// different enough cadences to warrant separate cards, and this keeps
// Evaluation.tsx from growing past its current size.
//
// On-demand generation only (a button), same pattern as Evaluation's
// "Generate today's evaluation" -- no auto-trigger, no scheduled/proactive
// runs (confirmed decision).
//
// Deliberately NO per-day breakdown inside this view, and the velocity
// trend below is deliberately terse (week-granularity, capped bars) --
// a psychologist consult flagged day-over-day comparison charts as
// OCD rumination bait for this user; a denser view here would repeat
// that mistake at a coarser but still risky granularity.

export function Retro() {
  const [result, setResult] = useState<WeeklyRetroOut | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<WeeklyRetroOut[] | null>(null);

  async function refreshHistory() {
    try {
      const data = await apiGet<WeeklyRetroOut[]>("/retro/history?weeks=6");
      setHistory(data);
    } catch {
      // Non-critical -- the velocity trend just stays empty if this fails.
    }
  }

  useEffect(() => {
    refreshHistory();
  }, []);

  async function handleGenerate() {
    setPending(true);
    setError(null);
    try {
      const generated = await apiPost<WeeklyRetroOut>("/retro/generate", {});
      setResult(generated);
      await refreshHistory();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't generate this week's retro.");
    } finally {
      setPending(false);
    }
  }

  const trendWeeks = (history ?? []).slice().reverse();
  const maxFocusedMinutes = Math.max(1, ...trendWeeks.map((w) => w.focused_minutes));

  return (
    <section className="retro" id="retro">
      <h2>Week review</h2>

      <div className="retro__report">
        <button type="button" className="retro__generate" disabled={pending} onClick={handleGenerate}>
          {pending ? "Generating…" : "Generate this week's retro"}
        </button>

        {error && <p className="retro__error">{error}</p>}

        {result && (
          <div className="retro__result">
            <div className="retro__metrics">
              <div className="retro__metric">
                <span className="retro__metric-label">Sessions</span>
                <span className="retro__metric-value">{result.sessions_count}</span>
              </div>
              <div className="retro__metric">
                <span className="retro__metric-label">Focused time</span>
                <span className="retro__metric-value">{result.focused_minutes.toFixed(0)} min</span>
              </div>
              <div className="retro__metric">
                <span className="retro__metric-label">Committed this week</span>
                <span className="retro__metric-value">
                  {result.committed_completed_count}/{result.committed_count}
                </span>
              </div>
              <div className="retro__metric">
                <span className="retro__metric-label">Mood avg</span>
                <span className="retro__metric-value">
                  {result.mood_avg === null ? "—" : result.mood_avg.toFixed(1)}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {trendWeeks.length > 0 && (
        <div className="retro__velocity">
          <p className="retro__trend-label">Last {trendWeeks.length} weeks</p>
          <div className="retro__velocity-rows">
            {trendWeeks.map((w) => (
              <div key={w.week_start} className="retro__velocity-row">
                <span className="retro__velocity-week">
                  {new Date(w.week_start).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </span>
                <div className="retro__velocity-track">
                  <div
                    className="retro__velocity-bar"
                    style={{ width: `${Math.max(4, (w.focused_minutes / maxFocusedMinutes) * 100)}%` }}
                  />
                </div>
                <span className="retro__velocity-value">
                  {w.focused_minutes.toFixed(0)}m · {w.tasks_completed_count} done
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default Retro;
