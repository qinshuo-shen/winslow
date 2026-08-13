import { useEffect, useState } from "react";
import { apiGet, apiPatch, apiPost, ApiError } from "../../api/client";
import type { BacklogTaskOut, PMReviewOut, PMSuggestionOut } from "../../api/types";
import "./PMAgentPanel.css";

// AI PM-agent (Scrum-lite feature set) -- a deliberate, on-demand paid
// action (no polling, no auto-trigger, no proactive/scheduled runs --
// confirmed decision), unlike the passive reminder banners elsewhere in
// this app. "Apply" on a suggestion is literally the same
// PATCH /api/backlog/{id} the Board itself uses -- this component has no
// special write path, matching pm_agent.py's own "suggest, never
// auto-act" enforcement on the backend.

interface PMAgentPanelProps {
  onTaskApplied?: () => void;
}

export function PMAgentPanel({ onTaskApplied }: PMAgentPanelProps) {
  const [review, setReview] = useState<PMReviewOut | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [applyingId, setApplyingId] = useState<string | null>(null);

  useEffect(() => {
    apiGet<PMReviewOut>("/pm-agent/last")
      .then(setReview)
      .catch(() => {
        // 404 (nothing generated yet) or any other fetch failure -- just
        // stay in the "no review yet" state, no error shown for this.
      });
  }, []);

  async function handleReview() {
    setPending(true);
    setError(null);
    try {
      const result = await apiPost<PMReviewOut>("/pm-agent/review");
      setReview(result);
      setDismissedIds(new Set());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't review the backlog.");
    } finally {
      setPending(false);
    }
  }

  async function handleApply(s: PMSuggestionOut) {
    if (!s.suggested_action) return;
    setApplyingId(s.id);
    setError(null);
    try {
      await apiPatch<BacklogTaskOut>(`/backlog/${s.task_id}`, s.suggested_action);
      setDismissedIds((prev) => new Set(prev).add(s.id));
      onTaskApplied?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't apply that suggestion.");
    } finally {
      setApplyingId(null);
    }
  }

  function handleDismiss(id: string) {
    setDismissedIds((prev) => new Set(prev).add(id));
  }

  const visibleSuggestions = (review?.suggestions ?? []).filter((s) => !dismissedIds.has(s.id));

  return (
    <section className="pm-agent">
      <div className="pm-agent__header">
        <h2>Backlog review</h2>
        <button type="button" className="pm-agent__review" disabled={pending} onClick={handleReview}>
          {pending ? "Reviewing…" : "Review my backlog"}
        </button>
      </div>

      {error && <p className="pm-agent__error">{error}</p>}

      {review && (
        <p className="pm-agent__meta">
          Last reviewed {new Date(review.generated_at).toLocaleString(undefined, {
            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
          })}
          {review.model_used !== "mock" && ` · ${review.model_used}`}
        </p>
      )}

      {visibleSuggestions.length > 0 && (
        <ul className="pm-agent__suggestions">
          {visibleSuggestions.map((s) => (
            <li key={s.id} className="pm-agent__card">
              <div className="pm-agent__card-row">
                <p className="pm-agent__card-title">{s.title}</p>
                <button
                  type="button"
                  className="pm-agent__dismiss"
                  onClick={() => handleDismiss(s.id)}
                  aria-label="Dismiss suggestion"
                >
                  ×
                </button>
              </div>
              <p className="pm-agent__card-rationale">{s.rationale}</p>
              {s.suggested_action && (
                <button
                  type="button"
                  className="pm-agent__apply"
                  disabled={applyingId === s.id}
                  onClick={() => handleApply(s)}
                >
                  {applyingId === s.id ? "Applying…" : "Apply"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default PMAgentPanel;
