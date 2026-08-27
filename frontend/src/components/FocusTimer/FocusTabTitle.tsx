import { useEffect, useRef } from "react";
import { useFocusPolling } from "./useFocusPolling";
import { SILENT_LOOP_WAV } from "./silentLoop";

// Mirrors the live focus/pause countdown into document.title so it's visible
// from another browser tab. Mounted once in Layout.tsx (NOT in
// FocusTimerWidget) so it survives client-side route changes -- when it lived
// in the widget, navigating away from /focus unmounted it and the countdown
// vanished from the tab.
//
// The displayed value is interpolated locally from the last poll's anchor
// (remaining_seconds / pause_auto_fail_in_seconds + the wall-clock time it
// was received), repainted every 1s by setInterval and immediately whenever
// the tab/window regains focus.
//
// Background-tab freezing: browsers throttle and eventually freeze
// setInterval in a fully hidden tab (~5 min), which is exactly when the
// tab-title countdown matters. To keep it ticking, while a session is
// running/paused we loop a near-silent audio clip (see silentLoop.ts) --
// that makes the browser treat the tab as "playing audio" and exempt it
// from the freeze. The tab shows a speaker icon while a session runs; that's
// the accepted trade-off. If autoplay is blocked (session resumed on a cold
// page load with no prior interaction), playback starts on the first user
// gesture instead.
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
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const wantAudioRef = useRef(false);

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

  // Repaint the title from the anchor: on a 1s interval, and immediately when
  // the tab/window regains focus (interval may have been throttled/frozen).
  useEffect(() => {
    const render = () => {
      const a = anchorRef.current;
      if (!a) return;
      const remaining = Math.max(0, a.secs - (Date.now() - a.at) / 1000);
      document.title = `${a.mode === "running" ? "▶" : "⏸"} ${formatMMSS(remaining)} — Winslow`;
    };
    render();
    const id = setInterval(render, 1000);
    const onVisibility = () => {
      if (!document.hidden) render();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", render);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", render);
    };
  }, []);

  // Silent-audio keep-alive while a session is running/paused.
  useEffect(() => {
    wantAudioRef.current = state?.status === "running" || state?.status === "paused";
    if (wantAudioRef.current) {
      if (!audioRef.current) {
        const a = new Audio(SILENT_LOOP_WAV);
        a.loop = true;
        a.volume = 0.05;
        audioRef.current = a;
      }
      audioRef.current.play().catch(() => {
        // Autoplay blocked (no prior interaction) -- the gesture listener
        // below will retry on the first click/keypress.
      });
    } else {
      audioRef.current?.pause();
    }
  }, [state?.status]);

  // If autoplay was blocked on a cold load, start the keep-alive on the
  // first user gesture. Listener lives for the component's (Layout's) life.
  useEffect(() => {
    const onGesture = () => {
      if (wantAudioRef.current) audioRef.current?.play().catch(() => {});
    };
    document.addEventListener("pointerdown", onGesture);
    document.addEventListener("keydown", onGesture);
    return () => {
      document.removeEventListener("pointerdown", onGesture);
      document.removeEventListener("keydown", onGesture);
      audioRef.current?.pause();
      audioRef.current = null;
    };
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
