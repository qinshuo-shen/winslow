import { useOutletContext } from "react-router-dom";
import { Evaluation } from "../components/Evaluation/Evaluation";
import { Retro } from "../components/Retro/Retro";
import type { LayoutOutletContext } from "../components/Layout/Layout";

// 2026-08 page-split redesign (Page 4, "Daily and weekly evaluation").
// moodRefreshKey comes from Layout via Outlet context, needed for the one
// real cross-route case: logging a mood through the global EndOfDayReminder
// banner while already sitting on this page -- Evaluation's own
// useEffect(..., [moodRefreshKey]) re-fetches when it changes. Every other
// path (navigating here fresh) already refetches on mount for free.
//
// Retro (weekly retro + velocity trend, Scrum-lite feature set) lands here
// as the literal "weekly" half of this page's stated purpose -- it's a
// standalone sibling component, not a modification of Evaluation, same
// separation its own file header already documents. Correction to an
// earlier note on this page: the "Scrum-lite doesn't exist" finding was
// based on a stale local checkout that was missing this feature's commit
// (already on origin/master) -- reconciled the same day.

export function EvaluationPage() {
  const { moodRefreshKey } = useOutletContext<LayoutOutletContext>();
  return (
    <>
      <Evaluation moodRefreshKey={moodRefreshKey} />
      <Retro />
    </>
  );
}

export default EvaluationPage;
