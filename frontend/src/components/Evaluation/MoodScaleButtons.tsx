import { useState } from "react";
import { apiPost, ApiError } from "../../api/client";
import type { MoodCreateRequest } from "../../api/types";

// Extracted from Evaluation.tsx (originally inline) so the end-of-day
// reminder banner (EndOfDayReminder.tsx) can offer the exact same one-tap
// mood logging without duplicating/diverging from the full Evaluation
// section's copy of it.
//
// Deliberately no emoji/game framing on the mood scale (1-5 plain numbers)
// -- same "calm, not gamified" tone the Board/former-Now surface already
// established for this redesign. `compact` hides the optional note field
// for contexts (the reminder banner) that want a true single-tap action
// rather than a small form.

const MOOD_SCALE = [1, 2, 3, 4, 5];

interface MoodScaleButtonsProps {
  compact?: boolean;
  onLogged?: () => void;
}

export function MoodScaleButtons({ compact = false, onLogged }: MoodScaleButtonsProps) {
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleLogMood(score: number) {
    setPending(true);
    setError(null);
    try {
      const body: MoodCreateRequest = { mood_score: score, note: note.trim() };
      await apiPost("/mood", body);
      setNote("");
      onLogged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't log that.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mood-scale-buttons">
      <div className="evaluation__mood-scale">
        {MOOD_SCALE.map((score) => (
          <button
            key={score}
            type="button"
            disabled={pending}
            onClick={() => handleLogMood(score)}
            className="evaluation__mood-button"
          >
            {score}
          </button>
        ))}
      </div>
      {!compact && (
        <input
          type="text"
          placeholder="Optional note…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={pending}
          className="evaluation__mood-note"
        />
      )}
      {error && <p className="evaluation__error">{error}</p>}
    </div>
  );
}

export default MoodScaleButtons;
