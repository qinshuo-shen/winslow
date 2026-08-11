// TypeScript interfaces mirroring every pydantic model in api/schemas.py.
// Kept in sync by hand (no codegen at this size) -- see api/schemas.py for
// the source of truth. Dates/datetimes come back from FastAPI as ISO 8601
// strings, not Date objects.

export interface TaskOut {
  page_id: string;
  name: string;
  priority: string | null;
  start_date: string; // date
  notes: string;
  url: string;
  specific_project: string | null;
  assigned_count: number;
}

export interface WeekRangeOut {
  today: string; // date
  week_end: string; // date
  days: string[]; // date[]
}

export interface CalendarEventOut {
  uid: string;
  summary: string;
  start: string; // datetime
  end: string; // datetime
  notes: string;
}

export interface RowOut {
  start: string; // datetime
  work_end: string; // datetime
  break_end: string; // datetime
}

export type RowStatus = "empty" | "assigned" | "busy";

export interface RowStateOut {
  row: RowOut;
  status: RowStatus;
  event: CalendarEventOut | null;
  busy_summary: string | null;
}

export interface GridOut {
  day: string; // date
  check_conflicts: boolean;
  rows: RowStateOut[];
}

export interface SessionOut {
  id: number;
  start_time: string; // datetime
  end_time: string; // datetime
  planned_minutes: number;
  actual_minutes: number;
  completed: boolean;
  task_label: string | null;
  wheel_result: string | null;
  outcome: string | null;
  runes_awarded: number;
  specific_project: string | null;
}

export interface StatsOut {
  sessions: number;
  completion_rate: number | null;
  focused_minutes: number;
  daily_minutes: Record<string, number>;
}

export interface CharacterOut {
  runes: number;
  level: number;
  stats: Record<string, number>;
  next_costs: Record<string, number>;
}

export interface BloodstainOut {
  id: number;
  runes: number;
  created_at: string; // datetime
  session_id: number | null;
}

export interface QuestlineOut {
  project_name: string;
  session_count: number;
  milestones_paid: number;
}

export interface GearOut {
  gear_id: string;
  name: string;
  cost: number;
  min_level: number;
  flavor_text: string;
  owned: boolean;
  can_buy: boolean;
}

export interface StatRestRequest {
  stat_name: string;
}

// Phase 4: planner drag-and-drop request/response bodies.

export interface AssignedEventOut {
  uid: string;
  summary: string;
  start: string; // datetime
  end: string; // datetime
  notes: string;
}

export interface AssignRequest {
  page_id: string;
  day: string; // date
  row_start: string; // datetime
  row_end: string; // datetime
}

export interface MoveRequest {
  uid: string;
  day: string; // date
  row_start: string; // datetime
  row_end: string; // datetime
}

export interface DeleteAssignOut {
  deleted: boolean;
}

export interface PlannerRefreshOut {
  removed_count: number;
  log: string[];
}

export interface CompleteTaskOut {
  removed_blocks: number;
}

// Phase 5: browser-drivable focus timer.

export type FocusStatus = "idle" | "running" | "paused";

export interface SessionResultOut {
  completed: boolean;
  actual_minutes: number;
  wheel_result: string | null;
  outcome: string;
  runes_awarded: number;
}

export interface FocusStateOut {
  status: FocusStatus;
  task_label: string | null;
  priority: string | null;
  specific_project: string | null;
  duration_minutes: number | null;
  remaining_seconds: number | null;
  paused_seconds: number | null;
  pause_auto_fail_in_seconds: number | null;
  last_result: SessionResultOut | null;
  hardcore: boolean;
}

export interface FocusStartRequest {
  duration_minutes: number;
  task_label?: string | null;
  priority?: string | null;
  specific_project?: string | null;
  hardcore?: boolean;
}

// 2026-08-11 redesign: native task backlog (replaces Notion) + the
// proactive-nudge "Now" surface. PRIORITY_QUADRANTS's 4 strings must match
// notion_tasks.PRIORITY_ORDER's *set* exactly (the backend validates
// against these strings via membership, not position) -- kept here, not
// derived, same "no codegen at this size" convention as the rest of this
// file. This array's ORDER is purely the Board's display order (quadrant
// column order, and the add-task <select>'s option order) -- confirmed
// with the user, matching their Notion dashboard's layout -- and is
// intentionally different from notion_tasks.PRIORITY_ORDER's order, which
// is effort-first for the backend's actionable-task ranking and unrelated
// to how columns are laid out on screen.

export const PRIORITY_QUADRANTS = [
  "Quick Wins (High Impact-Low Effort)",
  "Major Projects (High Impact-High Effort)",
  "Fill-ins (Low Impact-Low Effort)",
  "Thankless Tasks (Low Impact-High Effort)",
] as const;

export type PriorityQuadrant = (typeof PRIORITY_QUADRANTS)[number];

export function quadrantLabel(priority: string): string {
  // "Quick Wins (High Impact-Low Effort)" -> "Quick Wins" -- the parenthetical
  // is there for backend/notion_tasks compatibility, not for display.
  return priority.split(" (")[0];
}

export type TaskStatus = "not_started" | "in_progress" | "on_hold" | "completed";

export const TASK_STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "not_started", label: "Not Started" },
  { value: "in_progress", label: "In Progress" },
  { value: "on_hold", label: "On hold" },
  { value: "completed", label: "Done" },
];

export interface BacklogTaskOut {
  id: number;
  name: string;
  priority: string;
  effort_minutes: number;
  notes: string;
  status: TaskStatus;
  created_at: string; // datetime
  specific_project: string | null;
  is_today: boolean;
  position: number;
  completed_at: string | null; // datetime
  tags: string[];
}

export interface BacklogTaskCreateRequest {
  name: string;
  priority: string;
  notes?: string;
  specific_project?: string | null;
  tags?: string[];
}

// Board (2026-08-11 redesign, same-day follow-up): PATCH /api/backlog/{id}
// -- every field optional, only what's set is changed. `tags`, if present,
// REPLACES the task's full tag set (not a merge).
export interface BacklogTaskUpdateRequest {
  name?: string;
  priority?: string;
  notes?: string;
  status?: TaskStatus;
  specific_project?: string | null;
  is_today?: boolean;
  position?: number;
  tags?: string[];
}

// Fourth same-day follow-up: two-level tag hierarchy (Project / sub-project).
// `parent` is null for a top-level "Project" tag (e.g. "PhD core"); a
// non-null `parent` names the top-level tag this one is nested under.

export interface TagOut {
  name: string;
  parent: string | null;
}

export interface TagCreateRequest {
  name: string;
  parent?: string | null;
}

// Same-day follow-up: end-of-day evaluation + mood tracker (3/3.1/3.2).

export interface MoodEntryOut {
  id: number;
  ts: string; // datetime
  mood_score: number; // 1-5
  note: string;
}

export interface MoodCreateRequest {
  mood_score: number;
  note?: string;
}

export interface DailyEvaluationOut {
  date: string; // date
  generated_at: string; // datetime
  sessions_count: number;
  focused_minutes: number;
  completion_rate: number | null;
  tasks_completed_count: number;
  runes_earned: number;
  mood_avg: number | null;
  mood_entries: MoodEntryOut[];
  tasks_completed_names: string[];
  quadrant_breakdown: Record<string, number>;
}

export type NowStatus = "idle" | "pending_start";

export interface NowOut {
  status: NowStatus;
  task: BacklogTaskOut | null;
  auto_start_in_seconds: number | null;
  swap_count: number;
  max_swaps: number;
  deadline_at: string | null; // datetime -- the task's actual binding deadline (engagement, not completion)
}
