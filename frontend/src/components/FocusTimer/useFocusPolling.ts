import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, ApiError } from "../../api/client";
import type { FocusStateOut } from "../../api/types";

// Polls GET /api/focus/state every second. The backend's own lifespan
// background task (api/main.py) is what actually drives auto-complete/
// auto-fail transitions on schedule -- this hook's polling is purely so a
// visible tab renders a live countdown and picks up state changes (start/
// pause/resume/stop from this tab, or a transition the background task
// just applied) within ~1s, not what makes those transitions happen.
//
// `refetch` is exposed so action handlers (start/pause/resume/stop) can
// force an immediate re-sync right after their own POST resolves, rather
// than waiting up to 1s for the next interval tick.

interface UseFocusPollingResult {
  state: FocusStateOut | null;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useFocusPolling(intervalMs = 1000): UseFocusPollingResult {
  const [state, setState] = useState<FocusStateOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  const refetch = useCallback(async () => {
    try {
      const data = await apiGet<FocusStateOut>("/focus/state");
      if (!cancelledRef.current) {
        setState(data);
        setError(null);
      }
    } catch (e) {
      if (!cancelledRef.current) {
        setError(e instanceof ApiError ? e.message : "Failed to load focus session state.");
      }
    }
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    refetch();
    const id = setInterval(refetch, intervalMs);
    return () => {
      cancelledRef.current = true;
      clearInterval(id);
    };
  }, [refetch, intervalMs]);

  return { state, error, refetch };
}
