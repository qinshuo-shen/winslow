import { useEffect, useRef, useState } from "react";
import { apiPost, ApiError } from "../../api/client";
import type { FocusStartRequest, FocusStateOut } from "../../api/types";
import { useAppData } from "../../context/AppDataContext";
import { useFocusPolling } from "./useFocusPolling";
import "./FocusTimerWidget.css";

// Browser-drivable focus timer (Phase 5) -- the web equivalent of the
// terminal `focus start` command, backed by focus_session_manager.manager
// via /api/focus/*. No Streamlit precedent for this section (app.py never
// had a focus timer at all -- see Phase 5's task description), so this UI
// is new, not ported. Kept intentionally simple: a duration + free-text
// label form, live countdown, pause/resume/stop -- no Notion task picker,
// no sound/animation.
//
// 2026-08-07: on a running/paused -> idle-with-result transition (session
// completed, failed, or stopped), refetch Character (Runes may have
// changed) and call onSessionEnd (bumps App.tsx's statsRefreshKey so
// FocusStats picks it up too). Detected via a status-transition effect over
// the polled state, not just inside runAction -- auto-complete/auto-fail
// happen on the backend's own tick loop and never go through runAction at
// all, so watching the poll is the only way to catch every case.

interface FocusTimerWidgetProps {
  onSessionEnd?: () => void;
}

function formatMMSS(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const mm = Math.floor(seconds / 60);
  const ss = seconds % 60;
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

function completionMessage(result: NonNullable<FocusStateOut["last_result"]>): string {
  if (result.outcome === "completed") {
    return `Session complete! +${result.runes_awarded} Runes (${result.actual_minutes.toFixed(1)} min).`;
  }
  if (result.outcome === "failed_pause_timeout") {
    return `Session failed -- paused too long. ${result.actual_minutes.toFixed(1)} min logged, Runes left in a bloodstain.`;
  }
  return `Session stopped early. ${result.actual_minutes.toFixed(1)} min logged (no reward this time).`;
}

export function FocusTimerWidget({ onSessionEnd }: FocusTimerWidgetProps) {
  const { state, error: pollError, refetch } = useFocusPolling(1000);
  const { refetchCharacter } = useAppData();
  const [duration, setDuration] = useState("25");
  const [taskLabel, setTaskLabel] = useState("");
  const [hardcore, setHardcore] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const prevStatusRef = useRef<FocusStateOut["status"] | null>(null);
  useEffect(() => {
    if (!state) return;
    const wasActive = prevStatusRef.current === "running" || prevStatusRef.current === "paused";
    if (wasActive && state.status === "idle" && state.last_result) {
      refetchCharacter();
      onSessionEnd?.();
    }
    prevStatusRef.current = state.status;
  }, [state, refetchCharacter, onSessionEnd]);

  async function runAction(fn: () => Promise<unknown>) {
    setPending(true);
    setActionError(null);
    try {
      await fn();
      await refetch();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  function handleStart(e: React.FormEvent) {
    e.preventDefault();
    const minutes = parseFloat(duration);
    if (!minutes || minutes <= 0) {
      setActionError("Enter a valid duration in minutes.");
      return;
    }
    const body: FocusStartRequest = {
      duration_minutes: minutes,
      task_label: taskLabel.trim() || null,
      hardcore,
    };
    runAction(() => apiPost<FocusStateOut>("/focus/start", body));
  }

  const error = pollError ?? actionError;

  return (
    <section className="focus-timer">
      <h2>Focus timer</h2>

      {error && <p className="focus-timer__error">{error}</p>}

      {state === null && !error && <p className="focus-timer__loading">Loading…</p>}

      {state !== null && state.last_result && state.status === "idle" && (
        <p className="focus-timer__result">{completionMessage(state.last_result)}</p>
      )}

      {state !== null && state.status === "idle" && (
        <form className="focus-timer__form" onSubmit={handleStart}>
          <label className="focus-timer__field">
            <span>Duration (min)</span>
            <input
              type="number"
              min="0.05"
              step="1"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              disabled={pending}
            />
          </label>
          <label className="focus-timer__field">
            <span>Task (optional)</span>
            <input
              type="text"
              value={taskLabel}
              onChange={(e) => setTaskLabel(e.target.value)}
              placeholder="What are you working on?"
              disabled={pending}
            />
          </label>
          <label className="focus-timer__field focus-timer__field--checkbox">
            <input
              type="checkbox"
              checked={hardcore}
              onChange={(e) => setHardcore(e.target.checked)}
              disabled={pending}
            />
            <span>🔒 Hardcore (block my calendar)</span>
          </label>
          <button type="submit" disabled={pending}>
            Start
          </button>
        </form>
      )}

      {state !== null && state.status === "running" && (
        <div className="focus-timer__active">
          <span className="focus-timer__countdown">
            {formatMMSS(state.remaining_seconds ?? 0)}
          </span>
          {state.task_label && (
            <span className="focus-timer__task-label">on "{state.task_label}"</span>
          )}
          {state.hardcore && <span className="focus-timer__hardcore-badge">🔒 Hardcore</span>}
          <div className="focus-timer__actions">
            <button
              type="button"
              disabled={pending}
              onClick={() => runAction(() => apiPost<FocusStateOut>("/focus/pause"))}
            >
              Pause
            </button>
            <button
              type="button"
              className="focus-timer__stop"
              disabled={pending}
              onClick={() => runAction(() => apiPost<FocusStateOut>("/focus/stop"))}
            >
              Stop
            </button>
          </div>
        </div>
      )}

      {state !== null && state.status === "paused" && (
        <div className="focus-timer__active focus-timer__active--paused">
          <span className="focus-timer__paused-label">
            PAUSED — auto-fails in {formatMMSS(state.pause_auto_fail_in_seconds ?? 0)}
          </span>
          <div className="focus-timer__actions">
            <button
              type="button"
              disabled={pending}
              onClick={() => runAction(() => apiPost<FocusStateOut>("/focus/resume"))}
            >
              Resume
            </button>
            <button
              type="button"
              className="focus-timer__stop"
              disabled={pending}
              onClick={() => runAction(() => apiPost<FocusStateOut>("/focus/stop"))}
            >
              Stop
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export default FocusTimerWidget;
