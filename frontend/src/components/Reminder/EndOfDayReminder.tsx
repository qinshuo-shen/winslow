import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MoodScaleButtons } from "../Evaluation/MoodScaleButtons";
import { useEndOfDayReminder } from "./useEndOfDayReminder";
import "./EndOfDayReminder.css";

// A passive, dismissible in-app reminder to log mood / generate today's
// evaluation, if neither has happened yet today -- explicitly NOT the old
// auto-pick-a-task-and-auto-start nudge engine (built and same-day
// rejected in this project's history for taking over task selection).
// This never auto-acts on anything; it only surfaces a one-tap action the
// user can take or dismiss.
//
// No time-of-day threshold by design -- shows any time today is unlogged,
// and the dismiss button is what handles "not now" rather than a fixed
// evening cutoff (one fewer constant to get wrong across devices/
// timezones). Dismissal is per-browser (localStorage), not app state --
// a UX preference, not data.
//
// notify.py's OS notification path is macOS-only (osascript) and Winslow's
// authoritative server now runs headless on a Linux VPS, so any
// server-triggered OS notification would silently no-op there -- this is
// a plain client-side banner instead, refreshed while a tab is open.

const DISMISS_KEY = "winslow.eod-reminder-dismissed";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

interface EndOfDayReminderProps {
  // Bumps Layout's moodRefreshKey so the Evaluation page's own mood list (a
  // separate component instance/state, possibly on a different route right
  // now) picks up a mood logged here too -- see Evaluation.tsx's
  // moodRefreshKey prop doc and Layout.tsx/EvaluationPage.tsx's Outlet
  // context wiring.
  onMoodLogged?: () => void;
}

export function EndOfDayReminder({ onMoodLogged }: EndOfDayReminderProps) {
  const { status, refetch } = useEndOfDayReminder();
  const navigate = useNavigate();

  function handleMoodLogged() {
    refetch();
    onMoodLogged?.();
  }
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === todayIso());

  // Re-check dismissal on the same "did the day change" signals the status
  // poll already uses, so a reminder dismissed yesterday reappears today.
  useEffect(() => {
    function checkDismissed() {
      setDismissed(localStorage.getItem(DISMISS_KEY) === todayIso());
    }
    document.addEventListener("visibilitychange", checkDismissed);
    return () => document.removeEventListener("visibilitychange", checkDismissed);
  }, []);

  if (!status || dismissed) return null;
  if (status.mood_logged || status.evaluation_generated) return null;

  function handleDismiss() {
    localStorage.setItem(DISMISS_KEY, todayIso());
    setDismissed(true);
  }

  function handleGenerateClick() {
    // 2026-08 page-split redesign: Evaluation now only renders on
    // /evaluation, so the old scrollIntoView("evaluation") would silently
    // no-op on every other route -- navigate there instead, the whole page
    // is the destination now, no in-page anchor needed.
    navigate("/evaluation");
  }

  return (
    <div className="eod-reminder">
      <div className="eod-reminder__row">
        <p className="eod-reminder__text">Haven't logged today yet -- how's it going?</p>
        <button
          type="button"
          className="eod-reminder__dismiss"
          onClick={handleDismiss}
          aria-label="Dismiss for today"
        >
          ×
        </button>
      </div>
      <MoodScaleButtons compact onLogged={handleMoodLogged} />
      <button type="button" className="eod-reminder__generate-link" onClick={handleGenerateClick}>
        Generate today's evaluation →
      </button>
    </div>
  );
}

export default EndOfDayReminder;
