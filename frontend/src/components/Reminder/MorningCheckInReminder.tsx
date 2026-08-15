import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMorningCheckIn } from "./useMorningCheckIn";
import "./MorningCheckInReminder.css";

// A passive, dismissible in-app prompt to pull something into Today, if
// nothing has been yet -- the morning counterpart to EndOfDayReminder.tsx.
// Same shape and same reasoning: no time-of-day threshold, dismiss handles
// "not now," dismissal is per-browser (localStorage) not app state. Unlike
// the evening reminder, there's no single-tap action to offer here (no
// "MoodScaleButtons" equivalent) -- committing to a task means picking one
// on the Board, so the CTA navigates there instead of acting inline.
//
// 2026-08 page-split redesign: rendered globally in Layout.tsx (like
// EndOfDayReminder) rather than becoming Tasks-page content, so it's not
// lost by being on the "wrong" page. Its CTA originally did
// document.getElementById("board")?.scrollIntoView(...), which silently
// no-ops now that Board only renders on /tasks -- fixed to navigate there
// instead, same fix already applied to EndOfDayReminder's equivalent bug.

const DISMISS_KEY = "winslow.morning-checkin-dismissed";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function MorningCheckInReminder() {
  const { status } = useMorningCheckIn();
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === todayIso());

  useEffect(() => {
    function checkDismissed() {
      setDismissed(localStorage.getItem(DISMISS_KEY) === todayIso());
    }
    document.addEventListener("visibilitychange", checkDismissed);
    return () => document.removeEventListener("visibilitychange", checkDismissed);
  }, []);

  if (!status || dismissed) return null;
  if (status.has_today_tasks) return null;

  function handleDismiss() {
    localStorage.setItem(DISMISS_KEY, todayIso());
    setDismissed(true);
  }

  function handleGoToBoard() {
    navigate("/tasks");
  }

  return (
    <div className="morning-checkin">
      <div className="morning-checkin__row">
        <p className="morning-checkin__text">Nothing pulled into Today yet -- what are you committing to?</p>
        <button
          type="button"
          className="morning-checkin__dismiss"
          onClick={handleDismiss}
          aria-label="Dismiss for today"
        >
          ×
        </button>
      </div>
      <button type="button" className="morning-checkin__board-link" onClick={handleGoToBoard}>
        Go to the Board →
      </button>
    </div>
  );
}

export default MorningCheckInReminder;
