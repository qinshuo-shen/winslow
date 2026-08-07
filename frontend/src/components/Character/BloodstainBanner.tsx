import type { BloodstainOut } from "../../api/types";
import "./BloodstainBanner.css";

// Mirrors app.py's active-bloodstain st.warning exactly (same 🩸 + message
// text); renders nothing when there's no active bloodstain, same as
// app.py's `if stain:` guard.

interface BloodstainBannerProps {
  bloodstain: BloodstainOut | null;
}

export function BloodstainBanner({ bloodstain }: BloodstainBannerProps) {
  if (bloodstain === null) return null;
  return (
    <p className="bloodstain-banner">
      🩸 Active bloodstain: {bloodstain.runes} Runes waiting to be recovered by your next
      completed focus session.
    </p>
  );
}

export default BloodstainBanner;
