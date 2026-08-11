import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, ApiError } from "../../api/client";
import type { NowOut } from "../../api/types";

// Polls GET /api/now every second -- same "poll the server's own tick loop,
// don't drive state locally" pattern as useFocusPolling. The backend's
// proactive_scheduler.tick() (api/main.py's lifespan) is what actually arms/
// advances a nudge; this hook just keeps a visible tab's countdown and
// Start/Swap availability in sync with it.

interface UseNowPollingResult {
  now: NowOut | null;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useNowPolling(intervalMs = 1000): UseNowPollingResult {
  const [now, setNow] = useState<NowOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  const refetch = useCallback(async () => {
    try {
      const data = await apiGet<NowOut>("/now");
      if (!cancelledRef.current) {
        setNow(data);
        setError(null);
      }
    } catch (e) {
      if (!cancelledRef.current) {
        setError(e instanceof ApiError ? e.message : "Failed to load the nudged task.");
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

  return { now, error, refetch };
}
