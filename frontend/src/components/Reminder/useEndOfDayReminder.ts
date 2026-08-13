import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, ApiError } from "../../api/client";
import type { EvaluationTodayStatusOut } from "../../api/types";

// Same cancelledRef/useCallback-refetch idiom as useFocusPolling/
// useNowPolling, but at a far coarser cadence -- this only needs to flip
// once a day, not track a live countdown. Refetches on mount, whenever the
// tab becomes visible again (covers "left it open all day, comes back at
// night"), and on a long interval backstop for a tab that's never
// blurred/refocused.

interface UseEndOfDayReminderResult {
  status: EvaluationTodayStatusOut | null;
  error: string | null;
  refetch: () => Promise<void>;
}

const BACKSTOP_INTERVAL_MS = 30 * 60 * 1000;

export function useEndOfDayReminder(): UseEndOfDayReminderResult {
  const [status, setStatus] = useState<EvaluationTodayStatusOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  const refetch = useCallback(async () => {
    try {
      const data = await apiGet<EvaluationTodayStatusOut>("/evaluation/today-status");
      if (!cancelledRef.current) {
        setStatus(data);
        setError(null);
      }
    } catch (e) {
      if (!cancelledRef.current) {
        setError(e instanceof ApiError ? e.message : "Failed to load today's evaluation status.");
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
