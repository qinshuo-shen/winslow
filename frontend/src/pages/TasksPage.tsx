import { useState } from "react";
import { Board } from "../components/Board/Board";
import { PMAgentPanel } from "../components/PMAgent/PMAgentPanel";

// 2026-08 page-split redesign (Page 1, "Tasks management and backlog
// review"). PMAgentPanel reviews and suggests changes to the backlog --
// exactly what this page is for -- so it lives here, directly below Board,
// same relative position it had in the old single-stacked App.tsx.
// boardRefreshKey stays same-page sibling state (both live on /tasks), no
// cross-route Outlet-context plumbing needed the way Evaluation's
// moodRefreshKey requires.

export function TasksPage() {
  const [boardRefreshKey, setBoardRefreshKey] = useState(0);

  return (
    <>
      <Board refreshKey={boardRefreshKey} />
      <PMAgentPanel onTaskApplied={() => setBoardRefreshKey((k) => k + 1)} />
    </>
  );
}

export default TasksPage;
