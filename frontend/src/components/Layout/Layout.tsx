import { useState } from "react";
import { Outlet } from "react-router-dom";
import { EndOfDayReminder } from "../Reminder/EndOfDayReminder";
import { MorningCheckInReminder } from "../Reminder/MorningCheckInReminder";
import { NavBar } from "./NavBar";
import "../../App.css";
import "./Layout.css";

// 2026-08 page-split redesign: the app's persistent shell (header, nav,
// morning/end-of-day reminders) wrapping whichever of the 4 routed pages
// (Tasks/Projects/Focus/Evaluation) is active -- moved verbatim out of the
// old App.tsx, which rendered every section stacked on one page.
//
// MorningCheckInReminder and EndOfDayReminder both stay global (rendered
// here, not inside a page) rather than becoming Tasks/Evaluation-page
// content -- they're proactive nudges the user shouldn't lose just for
// being on the "wrong" page, matching this project's own documented stance
// against reintroducing friction/decision points for its ADHD-aware design
// (see the push-based-redesign history).
// moodRefreshKey is threaded to EvaluationPage via Outlet context since
// that's the one page whose own on-mount refetch can't see a mood logged
// here while already mounted -- see EvaluationPage.tsx.

export interface LayoutOutletContext {
  moodRefreshKey: number;
}

export function Layout() {
  const [moodRefreshKey, setMoodRefreshKey] = useState(0);

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

      <NavBar />

      <MorningCheckInReminder />
      <EndOfDayReminder onMoodLogged={() => setMoodRefreshKey((k) => k + 1)} />

      <Outlet context={{ moodRefreshKey } satisfies LayoutOutletContext} />
    </div>
  );
}

export default Layout;
