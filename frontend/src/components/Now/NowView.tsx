import { useEffect, useState } from "react";
import { apiPost, ApiError } from "../../api/client";
import { quadrantLabel } from "../../api/types";
import type { NowOut } from "../../api/types";
import { useNowPolling } from "./useNowPolling";
import "./NowView.css";

// The new default view (2026-08-11 redesign) -- replaces "a dashboard you
// visit" with "the app tells you what to do next". Renders the proactively
// auto-picked task (see proactive_scheduler.py) with a plain-text countdown
// to auto-start and two actions: Start (large, primary -- the lowest-
// friction action available) and Swap (small, secondary, capped so this
// can't turn back into open-ended browsing). Calm/neutral by design -- see
// the redesign plan's UI direction: no urgency color, no guilt language,
// nothing that reads as a game.
//
// Renders nothing when there's no nudge pending (status === "idle") --
// TaskInput, rendered alongside this in App.tsx, is what a user reaches for
// in that state instead.

function formatMMSS(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const mm = Math.floor(seconds / 60);
  const ss = seconds % 60;
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

// Plain text, no color-coded urgency (per the "Quiet Momentum" UI
// direction) -- this is about engagement (did you work a session on it),
// not completion, so it shouldn't read as an alarm.
function formatDeadline(deadlineAt: string): string {
  const diffMs = new Date(deadlineAt).getTime() - Date.now();
  const hours = diffMs / (1000 * 60 * 60);
  if (hours < 0) return "due now";
  if (hours < 1) return `due in ${Math.round(hours * 60)} min`;
  if (hours < 24) return `due in ${Math.round(hours)}h`;
  return `due in ${Math.round(hours / 24)}d`;
}

interface NowViewProps {
  onSessionStarted?: () => void;
}

export function NowView({ onSessionStarted }: NowViewProps) {
  const { now, error: pollError, refetch } = useNowPolling(1000);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [displaySeconds, setDisplaySeconds] = useState<number | null>(null);

  // Countdown ticks locally between 1s polls so it doesn't visibly stall --
  // resynced to the server's own value on every poll, never drifts far.
  useEffect(() => {
    setDisplaySeconds(now?.auto_start_in_seconds ?? null);
  }, [now?.auto_start_in_seconds]);

  useEffect(() => {
    if (displaySeconds === null) return;
    const id = setInterval(() => {
      setDisplaySeconds((s) => (s === null ? null : Math.max(0, s - 1)));
    }, 1000);
    return () => clearInterval(id);
  }, [displaySeconds === null]);

  async function runAction(fn: () => Promise<NowOut>) {
    setPending(true);
    setActionError(null);
    try {
      await fn();
      await refetch();
      onSessionStarted?.();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  if (pollError) {
    return (
      <section className="now-view">
        <p className="now-view__error">{pollError}</p>
      </section>
    );
  }

  if (!now || now.status !== "pending_start" || !now.task) {
    return null;
  }

  const { task } = now;
  const swapsLeft = now.max_swaps - now.swap_count;

  return (
    <section className="now-view">
      <p className="now-view__eyebrow">{quadrantLabel(task.priority)}</p>
      <h2 className="now-view__title">{task.name}</h2>
      <p className="now-view__meta">
        ~{task.effort_minutes} min
        {now.deadline_at && <> · {formatDeadline(now.deadline_at)}</>}
        {displaySeconds !== null && (
          <> · starts on its own in {formatMMSS(displaySeconds)}</>
        )}
      </p>

      {actionError && <p className="now-view__error">{actionError}</p>}

      <div className="now-view__actions">
        <button
          type="button"
          className="now-view__start"
          disabled={pending}
          autoFocus
          onClick={() => runAction(() => apiPost<NowOut>("/now/start"))}
        >
          Start
        </button>
        {swapsLeft > 0 ? (
          <button
            type="button"
            className="now-view__swap"
            disabled={pending}
            onClick={() => runAction(() => apiPost<NowOut>("/now/swap"))}
          >
            Swap
          </button>
        ) : (
          <span className="now-view__swap-exhausted">that's the option for now</span>
        )}
      </div>
    </section>
  );
}

export default NowView;
