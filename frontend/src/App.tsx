import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { Layout } from "./components/Layout/Layout";
import { ProjectBoard } from "./components/Projects/ProjectBoard";
import { TasksPage } from "./pages/TasksPage";
import { FocusPage } from "./pages/FocusPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { LoginPage } from "./pages/LoginPage";
import { AuthProvider, useAuth } from "./auth/AuthContext";

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
//
// 2026-08 page-split redesign: the single stacked dashboard above became
// overwhelming, so it's split into 4 routed pages (Tasks/Projects/Focus/
// Evaluation) via React Router -- a deliberate departure from this app's
// prior "single dashboard page, no client router" convention (see
// api/main.py's docstring history). App.tsx is now just route
// definitions; the header/nav/EndOfDayReminder shell that used to live
// here moved to components/Layout/Layout.tsx, rendered once and shared
// across every route via an <Outlet />.
//
// Reconciled same day with the Scrum-lite feature set (sprints/retro/
// velocity/AI PM-agent, built in parallel on origin/master while this
// split was in progress on a stale local checkout): MorningCheckInReminder
// joined EndOfDayReminder in Layout.tsx (global, same "don't lose a
// proactive nudge to routing" reasoning); PMAgentPanel moved into
// pages/TasksPage.tsx alongside Board, since backlog review is literally
// what Page 1 is for; Retro moved into EvaluationPage.tsx alongside
// Evaluation, the "weekly" half of Page 4's stated purpose.

// Multi-user follow-up: gates the whole routed-page group behind a
// logged-in session -- AuthContext's one-time GET /api/auth/me on mount
// is what `loading` reflects here, so an unauthenticated visitor sees
// nothing flash before landing on /login, and everyone else falls through
// to the real pages below unchanged.
function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return null;
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/tasks" replace />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/projects" element={<ProjectBoard />} />
          <Route path="/focus" element={<FocusPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="*" element={<Navigate to="/tasks" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}

export default App;
