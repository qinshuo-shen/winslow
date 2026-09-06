import { Board } from "../components/Board/Board";
import { StandupPanel } from "../components/Standup/StandupPanel";

// 2026-08 page-split redesign (Page 1, "Tasks management and backlog
// review"). StandupPanel sits ABOVE Board -- it's the page's opening
// ritual (an optional question, then a generated forward-looking note or
// direct answer, no board data read and no task-mutation path).
//
// The old PMAgentPanel (a separate "Backlog review" AI feature, suggested
// changes with an Apply button) was removed from this page 2026-08-17 --
// its job was absorbed into StandupPanel's own question box instead of
// keeping two separate AI features (see standup.py's module docstring) --
// and deleted outright 2026-09-06 along with its backend, rather than
// being left on disk like this project's other retired modules. See
// api/main.py's comment at the router registrations for why that one got
// deleted instead of parked.

export function TasksPage() {
  return (
    <>
      <StandupPanel />
      <Board />
    </>
  );
}

export default TasksPage;
