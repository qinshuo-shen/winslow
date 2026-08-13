import { useState } from "react";
import { Board } from "./components/Board/Board";
import { FocusTimerWidget } from "./components/FocusTimer/FocusTimerWidget";
import { FocusStats } from "./components/FocusStats/FocusStats";
import { Evaluation } from "./components/Evaluation/Evaluation";
import { EndOfDayReminder } from "./components/Reminder/EndOfDayReminder";
import { MorningCheckInReminder } from "./components/Reminder/MorningCheckInReminder";
import { Retro } from "./components/Retro/Retro";
import { PMAgentPanel } from "./components/PMAgent/PMAgentPanel";
import "./App.css";

// 2026-08-11 redesign, same-day follow-up: replaces the old multi-panel
// "dashboard you visit" (Today's schedule, the manual drag-and-drop
// Planner grid, Character, Armory) AND the short-lived push-based "Now"
// nudge with a browsable, Notion-style Board (Today / Task Pool, grouped
// by Impact/Effort quadrant) -- the user's actual mental model for task
// planning, confirmed directly. Board replaces both NowView and TaskInput.
//
// TodaySchedule/Planner/CharacterPanel/ArmoryPanel/NowView are left on
// disk, unused, pending the redesign plan's Phase 6 cleanup -- removing
// them here was the goal (drop the RPG rewards system, the spin wheel, the
// grid, and the push nudge as the primary interaction), not a decision to
// also delete the files in this same pass.
//
// FocusTimerWidget/FocusStats are kept exactly as before -- FocusTimerWidget
// still doubles as the way to start an ad hoc/free-text session anytime.
// Evaluation is new: an end-of-day report + mood tracker appended below.
//
// Third same-day follow-up: AppDataProvider (Character/Runes context) is
// removed -- it existed solely for the RPG panels and FocusTimerWidget's
// post-session Character refetch, both gone now that Runes are removed.
//
// Fifth same-day follow-up: renamed "Procrastination Tool" -> "Winslow"
// ("win slow" -- a tortoise-and-hare pun, chosen by the user to go with
// the turtle mascot). The GitHub repo, pyproject.toml, and package.json
// were renamed to match; the internal Python package/import path
// (procrastination_tool/) and the local `~/Developer/procrastination-tool`
// directory were deliberately left alone -- pure internal plumbing with no
// user-facing naming benefit, and renaming either risks breaking the
// launchd plists' hardcoded paths (see launchd/*.plist) across both Macs.

function App() {
  const [statsRefreshKey, setStatsRefreshKey] = useState(0);
  const [moodRefreshKey, setMoodRefreshKey] = useState(0);
  const [boardRefreshKey, setBoardRefreshKey] = useState(0);

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>
          <span className="dashboard__title-mascot" aria-hidden="true">
            🐢
          </span>
          <span className="dashboard__title-text">Winslow</span>
        </h1>
        <p className="dashboard__date">
          {new Date().toLocaleDateString(undefined, {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
      </header>

      <MorningCheckInReminder />
      <EndOfDayReminder onMoodLogged={() => setMoodRefreshKey((k) => k + 1)} />
      <Board refreshKey={boardRefreshKey} />
      <PMAgentPanel onTaskApplied={() => setBoardRefreshKey((k) => k + 1)} />
      <FocusTimerWidget onSessionEnd={() => setStatsRefreshKey((k) => k + 1)} />
      <FocusStats refreshKey={statsRefreshKey} />
      <Evaluation moodRefreshKey={moodRefreshKey} />
      <Retro />
    </div>
  );
}

export default App;
