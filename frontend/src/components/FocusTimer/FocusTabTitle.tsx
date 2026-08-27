import { useEffect, useRef } from "react";
import { useFocusPolling } from "./useFocusPolling";

// Mirrors the live focus/pause countdown into document.title so it's visible
// from another browser tab. Mounted once in Layout.tsx (NOT in
// FocusTimerWidget) so it survives client-side route changes -- when it lived
// in the widget, navigating away from /focus unmounted it and the countdown
// vanished from the tab.
//
// The displayed value is interpolated locally on a 1s setInterval from the
// last poll's anchor (remaining_seconds / pause_auto_fail_in_seconds + the
// wall-clock time it was received), not written only when a poll lands. That
// keeps the title ticking every second even if useFocusPolling's fetch is
// slow or throttled (background tabs), and each fresh poll re-anchors so
// drift is corrected. Deep-background timer throttling is a browser limit we
// can't beat from JS; a poll on refocus re-syncs immediately.
//
// This does mean the app polls GET /api/focus/state every second on every
// page now, not just /focus. That's one tiny JSON GET/s -- fine for this
// app's scale.

function formatMMSS(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const mm = Math.floor(seconds / 60);
  const ss = seconds % 60;
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

interface Anchor {
  secs: number;
  at: number; // Date.now() when this value was received
  mode: "running" | "paused";
}

export function FocusTabTitle() {
  const { state } = useFocusPolling(1000);
  const originalTitleRef = useRef<string | null>(null);
  const anchorRef = useRef<Anchor | null>(null);

  if (originalTitleRef.current === null) {
    originalTitleRef.current = document.title;
  }

  // Re-anchor whenever the polled state changes; clear + restore when idle.
  useEffect(() => {
    if (state?.status === "running") {
      anchorRef.current = { secs: state.remaining_seconds ?? 0, at: Date.now(), mode: "running" };
    } else if (state?.status === "paused") {
      anchorRef.current = {
        secs: state.pause_auto_fail_in_seconds ?? 0,
        at: Date.now(),
        mode: "paused",
      };
    } else {
      anchorRef.current = null;
      if (originalTitleRef.current !== null) {
        document.title = originalTitleRef.current;
      }
    }
  }, [state?.status, state?.remaining_seconds, state?.pause_auto_fail_in_seconds]);

  // Local 1s ticker: interpolate the countdown from the anchor.
  useEffect(() => {
    const tick = () => {
      const a = anchorRef.current;
      if (!a) return;
      const remaining = Math.max(0, a.secs - (Date.now() - a.at) / 1000);
      const icon = a.mode === "running" ? "▶" : "⏸";
      document.title = `${icon} ${formatMMSS(remaining)} — Winslow`;
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  // Restore the original title if this ever unmounts.
  useEffect(() => {
    return () => {
      if (originalTitleRef.current !== null) {
        document.title = originalTitleRef.current;
      }
    };
  }, []);

  return null;
}

export default FocusTabTitle;
