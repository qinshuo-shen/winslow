import { Board } from "../components/Board/Board";
import { StandupPanel } from "../components/Standup/StandupPanel";

// 2026-08 page-split redesign (Page 1, "Tasks management and backlog
// review"). StandupPanel sits ABOVE Board -- it's the page's opening
// ritual (an optional question, then a generated forward-looking note or
// direct answer, no board data read and no task-mutation path).
//
// The old PMAgentPanel (a separate "Backlog review" AI feature, suggested
// changes with an Apply button) has been removed from this page -- its
// job was absorbed into StandupPanel's own question box instead of
// keeping two separate AI features (see standup.py's module docstring).
// procrastination_tool/pm_agent.py, api/routers/pm_agent.py, and
// PMAgentPanel.tsx are left on disk, unused, same convention as this
// project's other retired modules.

export function TasksPage() {
  return (
    <>
      <StandupPanel />
      <Board />
    </>
  );
}

export default TasksPage;
