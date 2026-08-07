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
}

export interface FocusStartRequest {
  duration_minutes: number;
  task_label?: string | null;
  priority?: string | null;
  specific_project?: string | null;
}
