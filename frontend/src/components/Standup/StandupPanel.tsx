import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { apiGet, apiPost, ApiError } from "../../api/client";
import type { StandupOut } from "../../api/types";
import "./StandupPanel.css";

// Virtual daily standup (Scrum-lite feature set) -- a deliberate, on-demand
// paid action, same "no polling, no auto-trigger" philosophy the old
// PMAgentPanel used. Also absorbed PMAgentPanel's backlog-review job (see
// standup.py's module docstring) -- the same free-text box now doubles as
// a general question box, not just a blockers field. Still structurally
// simpler than PMAgentPanel was, though: a standup response has no
// suggestion list and no task-mutation path at all, so there's no
// dismissedIds/applyingId/onTaskApplied here -- just today's note and a
// question field that's consumed by the one generate call, then cleared.

export function StandupPanel() {
  const [standup, setStandup] = useState<StandupOut | null>(null);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<StandupOut>("/standup/today")
      .then(setStandup)
      .catch(() => {
        // 404 (nothing generated yet today) or any other fetch failure --
        // just stay in the "no standup yet" state, no error shown for this.
      });
  }, []);

  async function handleGenerate() {
    setPending(true);
    setError(null);
    try {
      const result = await apiPost<StandupOut>("/standup/generate", { question });
      setStandup(result);
      // Clearing this reinforces the "ephemeral, consumed by that one
      // generation" contract visually, not just on the backend.
      setQuestion("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't generate today's standup.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="standup">
      <div className="standup__header">
        <h2>Standup</h2>
        <button
          type="button"
          className="standup__generate"
          disabled={pending}
          onClick={handleGenerate}
        >
          {pending ? "Generating…" : "Start standup"}
        </button>
      </div>

      <textarea
        className="standup__question"
        placeholder="Ask about today, your backlog, or anything blocking you… (optional)"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        disabled={pending}
        rows={2}
      />

      {error && <p className="standup__error">{error}</p>}

      {standup && (
        <>
          <p className="standup__meta">
            Generated {new Date(standup.generated_at).toLocaleString(undefined, {
              month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
            })}
            {standup.model_used !== "mock" && ` · ${standup.model_used}`}
          </p>
          <div className="standup__note">
            <ReactMarkdown>{standup.note}</ReactMarkdown>
          </div>
        </>
      )}

      {!standup && !pending && (
        <p className="standup__empty">
          No standup yet today — optionally ask something, then start.
        </p>
      )}
    </section>
  );
}

export default StandupPanel;
