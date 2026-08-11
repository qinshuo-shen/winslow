import { useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "../../api/client";
import type { DailyEvaluationOut, MoodCreateRequest, MoodEntryOut } from "../../api/types";
import { MoodTrendChart } from "./MoodTrendChart";
import "./Evaluation.css";

// End-of-day evaluation + mood tracker (3/3.1/3.2 in the redesign plan).
// Mood logging is available any time of day (not gated behind
// "generate"); the report itself is only computed on demand (the button),
// not auto-generated on page load, since it's meant to be a deliberate
// end-of-day reflection moment, not a live-updating dashboard tile.
//
// Deliberately no emoji/game framing on the mood scale (1-5 plain
// numbers) -- same "calm, not gamified" tone the Board/former-Now surface
// already established for this redesign.

const MOOD_SCALE = [1, 2, 3, 4, 5];

export function Evaluation() {
  const [todayMood, setTodayMood] = useState<MoodEntryOut[] | null>(null);
  const [moodPending, setMoodPending] = useState(false);
  const [moodNote, setMoodNote] = useState("");
  const [moodError, setMoodError] = useState<string | null>(null);

  const [evalResult, setEvalResult] = useState<DailyEvaluationOut | null>(null);
  const [evalPending, setEvalPending] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  const [history, setHistory] = useState<DailyEvaluationOut[] | null>(null);

  async function refreshMood() {
    try {
      const data = await apiGet<MoodEntryOut[]>("/mood");
      setTodayMood(data);
    } catch (e) {
      setMoodError(e instanceof ApiError ? e.message : "Couldn't load today's mood log.");
    }
  }

  async function refreshHistory() {
    try {
      const data = await apiGet<DailyEvaluationOut[]>("/evaluation/history?days=7");
      setHistory(data);
    } catch {
      // Non-critical -- the trend chart just stays empty if this fails.
    }
  }

  useEffect(() => {
    refreshMood();
    refreshHistory();
  }, []);

  async function handleLogMood(score: number) {
    setMoodPending(true);
    setMoodError(null);
    try {
      const body: MoodCreateRequest = { mood_score: score, note: moodNote.trim() };
      await apiPost("/mood", body);
      setMoodNote("");
      await refreshMood();
    } catch (e) {
      setMoodError(e instanceof ApiError ? e.message : "Couldn't log that.");
    } finally {
      setMoodPending(false);
    }
  }

  async function handleGenerate() {
    setEvalPending(true);
    setEvalError(null);
    try {
      const result = await apiPost<DailyEvaluationOut>("/evaluation/generate", {});
      setEvalResult(result);
      await refreshHistory();
    } catch (e) {
      setEvalError(e instanceof ApiError ? e.message : "Couldn't generate today's evaluation.");
    } finally {
      setEvalPending(false);
    }
  }

  const trendEntries = (history ?? [])
    .slice()
    .reverse()
    .map((e) => ({ date: e.date, moodAvg: e.mood_avg }));

  return (
    <section className="evaluation">
      <h2>Day review</h2>

      <div className="evaluation__mood">
        <h3>How are you feeling?</h3>
        <div className="evaluation__mood-scale">
          {MOOD_SCALE.map((score) => (
            <button
              key={score}
              type="button"
              disabled={moodPending}
              onClick={() => handleLogMood(score)}
              className="evaluation__mood-button"
            >
              {score}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Optional note…"
          value={moodNote}
          onChange={(e) => setMoodNote(e.target.value)}
          disabled={moodPending}
          className="evaluation__mood-note"
        />
        {moodError && <p className="evaluation__error">{moodError}</p>}

        {todayMood !== null && todayMood.length > 0 && (
          <ul className="evaluation__mood-list">
            {todayMood.map((m) => (
              <li key={m.id}>
                <span className="evaluation__mood-score">{m.mood_score}/5</span>
                <span className="evaluation__mood-time">
                  {new Date(m.ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                </span>
                {m.note && <span className="evaluation__mood-note-text">{m.note}</span>}
              </li>
            ))}
          </ul>
        )}

        {trendEntries.length > 0 && (
          <>
            <p className="evaluation__trend-label">Last {trendEntries.length} days</p>
            <MoodTrendChart entries={trendEntries} />
          </>
        )}
      </div>

      <div className="evaluation__report">
        <button
          type="button"
          className="evaluation__generate"
          disabled={evalPending}
          onClick={handleGenerate}
        >
          {evalPending ? "Generating…" : "Generate today's evaluation"}
        </button>

        {evalError && <p className="evaluation__error">{evalError}</p>}

        {evalResult && (
          <div className="evaluation__result">
            <div className="evaluation__metrics">
              <div className="evaluation__metric">
                <span className="evaluation__metric-label">Sessions</span>
                <span className="evaluation__metric-value">{evalResult.sessions_count}</span>
              </div>
              <div className="evaluation__metric">
                <span className="evaluation__metric-label">Focused time</span>
                <span className="evaluation__metric-value">
                  {evalResult.focused_minutes.toFixed(0)} min
                </span>
              </div>
              <div className="evaluation__metric">
                <span className="evaluation__metric-label">Completion rate</span>
                <span className="evaluation__metric-value">
                  {evalResult.completion_rate === null
                    ? "—"
                    : `${Math.round(evalResult.completion_rate * 100)}%`}
                </span>
              </div>
              <div className="evaluation__metric">
                <span className="evaluation__metric-label">Tasks completed</span>
                <span className="evaluation__metric-value">{evalResult.tasks_completed_count}</span>
              </div>
              <div className="evaluation__metric">
                <span className="evaluation__metric-label">Runes earned</span>
                <span className="evaluation__metric-value">{evalResult.runes_earned}</span>
              </div>
              <div className="evaluation__metric">
                <span className="evaluation__metric-label">Mood avg</span>
                <span className="evaluation__metric-value">
                  {evalResult.mood_avg === null ? "—" : evalResult.mood_avg.toFixed(1)}
                </span>
              </div>
            </div>

            {evalResult.tasks_completed_names.length > 0 && (
              <div className="evaluation__completed-tasks">
                <h4>Completed today</h4>
                <ul>
                  {evalResult.tasks_completed_names.map((name, i) => (
                    <li key={i}>{name}</li>
                  ))}
                </ul>
              </div>
            )}

            {Object.keys(evalResult.quadrant_breakdown).length > 0 && (
              <div className="evaluation__quadrant-breakdown">
                {Object.entries(evalResult.quadrant_breakdown).map(([label, count]) => (
                  <span key={label} className="evaluation__quadrant-chip">
                    {label}: {count}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export default Evaluation;
