import { useState } from "react";
import { FocusTimerWidget } from "../components/FocusTimer/FocusTimerWidget";
import { FocusStats } from "../components/FocusStats/FocusStats";

// 2026-08 page-split redesign: focus timer + stats, moved verbatim out of
// the old App.tsx (Page 3, "Focus session management"). onSessionEnd ->
// statsRefreshKey stays exactly as it was -- both components remain
// same-route siblings, so this cross-component link needed no rework
// under routing.

export function FocusPage() {
  const [statsRefreshKey, setStatsRefreshKey] = useState(0);

  return (
    <>
      <FocusTimerWidget onSessionEnd={() => setStatsRefreshKey((k) => k + 1)} />
      <FocusStats refreshKey={statsRefreshKey} />
    </>
  );
}

export default FocusPage;
