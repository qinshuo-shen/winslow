import { useState } from "react";
import { TodaySchedule } from "./components/TodaySchedule/TodaySchedule";
import { Planner } from "./components/Planner/Planner";
import { FocusTimerWidget } from "./components/FocusTimer/FocusTimerWidget";
import { FocusStats } from "./components/FocusStats/FocusStats";
import { CharacterPanel } from "./components/Character/CharacterPanel";
import { ArmoryPanel } from "./components/Armory/ArmoryPanel";
import { AppDataProvider } from "./context/AppDataContext";
import "./App.css";

// Phase 2 built the two read-only sections below -- "Today's schedule" and
// "Focus session stats". Phase 3 added the Character (with nested
// Questlines) and Armory sections. Phase 4 adds the Planner ("🗓️ Plan your
// week", the drag-and-drop grid) between Today's schedule and Focus
// sessions -- matching app.py's real section order exactly: Today's
// schedule, Plan your week, Focus sessions, Character, Armory. Character
// and Armory share live character state (Runes/level) via AppDataProvider,
// since an Armory purchase changes Runes that CharacterPanel displays, and
// vice versa for bonfire resting. Each existing component's own internals
// are untouched by this reorder.
//
// Phase 5 adds the FocusTimerWidget directly above FocusStats -- there's
// no Streamlit precedent for exact placement (app.py never had a focus
// timer section at all, see Phase 5's task description), but "start a
// session" naturally leads into "here's your history", matching the rest
// of the dashboard's top-to-bottom logical flow.
//
// 2026-08-07 optimization pass: AppDataProvider now wraps the whole
// dashboard (previously only CharacterPanel/ArmoryPanel) so FocusTimerWidget
// can refetchCharacter() after a session ends -- a completed/failed session
// awards or bloodstains Runes, which used to only show up in the Character
// panel after an unrelated manual reload. `statsRefreshKey` is a similarly
// minimal fix for FocusStats, which otherwise only fetches once on mount:
// FocusTimerWidget bumps it via onSessionEnd whenever a session transitions
// to idle-with-a-result (whether from a user action or the backend's own
// auto-complete/auto-fail tick), and FocusStats includes it in its fetch
// effect's dependencies. No new polling added on either end.

function App() {
  const [statsRefreshKey, setStatsRefreshKey] = useState(0);

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>Procrastination Tool</h1>
        <p className="dashboard__date">
          {new Date().toLocaleDateString(undefined, {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
      </header>

      <AppDataProvider>
        <TodaySchedule />
        <Planner />
        <FocusTimerWidget onSessionEnd={() => setStatsRefreshKey((k) => k + 1)} />
        <FocusStats refreshKey={statsRefreshKey} />

        <CharacterPanel />
        <ArmoryPanel />
      </AppDataProvider>
    </div>
  );
}

export default App;
