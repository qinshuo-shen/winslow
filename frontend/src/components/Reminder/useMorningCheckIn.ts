import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, ApiError } from "../../api/client";
import type { BacklogTodayStatusOut } from "../../api/types";

// Same cancelledRef/useCallback-refetch idiom as useEndOfDayReminder/
// useFocusPolling/useNowPolling -- see useEndOfDayReminder.ts for the full
// rationale. This is the morning counterpart: checks whether anything has
// been pulled into Today yet, not whether mood/evaluation has been logged.

interface UseMorningCheckInResult {
  status: BacklogTodayStatusOut | null;
  error: string | null;
  refetch: () => Promise<void>;
}

const BACKSTOP_INTERVAL_MS = 30 * 60 * 1000;

export function useMorningCheckIn(): UseMorningCheckInResult {
  const [status, setStatus] = useState<BacklogTodayStatusOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  const refetch = useCallback(async () => {
    try {
      const data = await apiGet<BacklogTodayStatusOut>("/backlog/today-status");
      if (!cancelledRef.current) {
        setStatus(data);
        setError(null);
      }
    } catch (e) {
      if (!cancelledRef.current) {
        setError(e instanceof ApiError ? e.message : "Failed to load today's task status.");
      }
    }
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    refetch();

    const id = setInterval(refetch, BACKSTOP_INTERVAL_MS);

    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        refetch();
      }
    }
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelledRef.current = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refetch]);

  return { status, error, refetch };
}
