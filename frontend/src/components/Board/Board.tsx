import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiGet, apiPatch, ApiError } from "../../api/client";
import { PRIORITY_QUADRANTS, quadrantLabel } from "../../api/types";
import type {
  BacklogTaskOut,
  BacklogTaskUpdateRequest,
  ProjectOut,
  TagOut,
  TaskStatus,
} from "../../api/types";
import { TaskCard } from "./TaskCard";
import { NotesModal } from "./NotesModal";
import { NewTaskModal } from "./NewTaskModal";
import { quadrantClass } from "./quadrantStyle";
import "./Board.css";

// The Board (2026-08-11 redesign, same-day follow-up) -- a browsable,
// Notion-style two-column layout (Today / Task Pool, each grouped by
// Impact/Effort quadrant) replacing both the old Notion-synced task list
// and the short-lived push-based "Now" nudge. See the redesign plan's
// Phase 0 note for why the nudge engine was pulled back out rather than
// kept alongside this.
//
// MVP interaction is button-based (status <select>, a Today⇄Pool toggle),
// not drag-and-drop -- @dnd-kit/core is already a dependency and could
// back a fast-follow reorder/drag interaction later using the same
// pattern the retired Planner/TaskPool components used, but buttons are
// lower-risk to ship correctly first.
//
// Adding a task (later same-day follow-up) is a single "+ Add task" button
// opening NewTaskModal, replacing the old always-visible three-field
// inline form -- name, quadrant, project, tags, and Markdown notes are all
// set up front in one place instead of adding a bare task then separately
// opening NotesModal afterward just to attach notes/tags.
//
// Project filter tabs (fourth same-day follow-up, later replaced by the
// draft-stage redesign below): a filter bar above the columns, one tab per
// real Project (procrastination_tool.projects), keyed off each task's
// `project_id` -- selecting one narrows the board to that project's tasks;
// "All" (default) shows everything, including project-less tasks. (This
// used to be driven by the tag hierarchy's top-level tags instead of real
// Projects -- tags remain fully editable elsewhere, just no longer drive
// this filter.)
//
// Draft-stage Roadmap steps: a task added via a Project's Roadmap
// quick-add can opt into starting as a draft (`is_draft`) instead of
// landing straight in the Task Pool. Drafts are excluded from the
// Today/Pool columns entirely and shown in their own "Drafts" section
// below them instead, narrowed by the same project tab, with a
// "Release to Pool" action per card.

interface BoardProps {
  onTasksChanged?: () => void;
  // Bumped by App.tsx whenever PMAgentPanel applies a suggestion (a PATCH
  // this component's own state doesn't know about) -- same lifted-
  // refreshKey pattern as Evaluation's moodRefreshKey.
  refreshKey?: number;
}

interface GroupedColumn {
  today: BacklogTaskOut[];
  pool: BacklogTaskOut[];
}

function groupByQuadrant(tasks: BacklogTaskOut[]): Record<string, GroupedColumn> {
  const groups: Record<string, GroupedColumn> = {};
  for (const q of PRIORITY_QUADRANTS) groups[q] = { today: [], pool: [] };
  for (const t of tasks) {
    const bucket = groups[t.priority] ?? (groups[t.priority] = { today: [], pool: [] });
    (t.is_today ? bucket.today : bucket.pool).push(t);
  }
  return groups;
}

function groupByDraftQuadrant(drafts: BacklogTaskOut[]): Record<string, BacklogTaskOut[]> {
  const groups: Record<string, BacklogTaskOut[]> = {};
  for (const q of PRIORITY_QUADRANTS) groups[q] = [];
  for (const t of drafts) {
    (groups[t.priority] ?? (groups[t.priority] = [])).push(t);
  }
  return groups;
}

export function Board({ onTasksChanged, refreshKey }: BoardProps) {
  const [tasks, setTasks] = useState<BacklogTaskOut[] | null>(null);
  const [tagTree, setTagTree] = useState<TagOut[]>([]);
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [sprintOnly, setSprintOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [notesTask, setNotesTask] = useState<BacklogTaskOut | null>(null);
  const [showNewTask, setShowNewTask] = useState(false);
  // Collapsed by default is wrong the first time a draft shows up (nothing
  // to hide yet), but stays expanded thereafter unless the user collapses
  // it themselves -- a large draft pool was dragging the page out, per the
  // user's own report.
  const [draftsCollapsed, setDraftsCollapsed] = useState(false);

  async function refresh() {
    try {
      const data = await apiGet<BacklogTaskOut[]>("/backlog");
      setTasks(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your task list.");
    }
  }

  async function refreshTags() {
    try {
      setTagTree(await apiGet<TagOut[]>("/tags"));
    } catch {
      // Non-critical -- the tag editor/project tabs just fall back to empty.
    }
  }

  async function refreshProjects() {
    try {
      setProjects(await apiGet<ProjectOut[]>("/projects"));
    } catch {
      // Non-critical -- the "Linked project" picker/chip just fall back to empty.
    }
  }

  useEffect(() => {
    refresh();
    refreshTags();
    refreshProjects();
  }, [refreshKey]);

  const projectNameById = useMemo(
    () => new Map(projects.map((p) => [p.id, p.name])),
    [projects],
  );

  const projectTabs = useMemo(
    () => [...projects].sort((a, b) => a.name.localeCompare(b.name)),
    [projects],
  );

  // Done tasks never appear on the Board -- they're historical record at
  // that point (especially post-Notion-migration, where completed tasks
  // badly outnumber open ones), not something to work from day to day.
  // Nothing is deleted, just excluded from this view; the evaluation
  // report's "tasks completed today" still counts them via completed_at.
  //
  // Draft steps are excluded here too (they get their own section below,
  // not the Today/Pool columns) -- see visibleDrafts.
  const visibleTasks = useMemo(() => {
    let notDone = (tasks ?? []).filter((t) => t.status !== "completed" && !t.is_draft);
    if (selectedProjectId !== null) {
      notDone = notDone.filter((t) => t.project_id === selectedProjectId);
    }
    if (sprintOnly) {
      notDone = notDone.filter((t) => t.is_current_week_commitment);
    }
    return notDone;
  }, [tasks, selectedProjectId, sprintOnly]);
  const grouped = useMemo(() => groupByQuadrant(visibleTasks), [visibleTasks]);

  // Draft Roadmap steps not yet released to the Task Pool -- narrowed by
  // the same project tab as Today/Pool, but not by the This Week toggle
  // (drafts aren't sprint-committed yet).
  const visibleDrafts = useMemo(() => {
    let drafts = (tasks ?? []).filter((t) => t.status !== "completed" && t.is_draft);
    if (selectedProjectId !== null) {
      drafts = drafts.filter((t) => t.project_id === selectedProjectId);
    }
    return drafts;
  }, [tasks, selectedProjectId]);
  const groupedDrafts = useMemo(() => groupByDraftQuadrant(visibleDrafts), [visibleDrafts]);

  async function patchTask(id: number, body: BacklogTaskUpdateRequest) {
    setPending(true);
    setError(null);
    try {
      const updated = await apiPatch<BacklogTaskOut>(`/backlog/${id}`, body);
      setTasks((prev) => prev?.map((t) => (t.id === id ? updated : t)) ?? prev);
      onTasksChanged?.();
      return updated;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't update that task.");
      return null;
    } finally {
      setPending(false);
    }
  }

  async function handleReleaseDraft(id: number) {
    await patchTask(id, { is_draft: false });
  }

  async function handleDelete(id: number) {
    setPending(true);
    setError(null);
    try {
      await apiDelete(`/backlog/${id}`);
      setTasks((prev) => prev?.filter((t) => t.id !== id) ?? prev);
      onTasksChanged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove that task.");
    } finally {
      setPending(false);
    }
  }

  function renderColumn(bucketKey: "today" | "pool", label: string) {
    return (
      <div className={`board__column board__column--${bucketKey}`}>
        <h3 className="board__column-title">{label}</h3>
        <div className="board__column-scroll">
        {PRIORITY_QUADRANTS.map((q) => {
          const items = grouped[q]?.[bucketKey] ?? [];
          return (
            <div key={q} className="board__quadrant">
              <h4 className={`board__quadrant-title board__quadrant-title--${quadrantClass(q)}`}>
                {quadrantLabel(q)}
              </h4>
              {items.length === 0 ? (
                <p className="board__quadrant-empty">Nothing here.</p>
              ) : (
                <ul className="board__quadrant-list">
                  {items.map((t) => (
                    <TaskCard
                      key={t.id}
                      task={t}
                      projectName={t.project_id !== null ? projectNameById.get(t.project_id) : undefined}
                      pending={pending}
                      onOpenNotes={() => setNotesTask(t)}
                      onStatusChange={(status: TaskStatus) => patchTask(t.id, { status })}
                      onPriorityChange={(priority: string) => patchTask(t.id, { priority })}
                      onToggleToday={() => patchTask(t.id, { is_today: !t.is_today })}
                      onToggleThisWeek={() => patchTask(t.id, { is_this_week: !t.is_this_week })}
                      onDelete={() => handleDelete(t.id)}
                    />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
        </div>
      </div>
    );
  }

  function renderDraftsSection() {
    return (
      <div className="board__drafts-section">
        <button
          type="button"
          className="board__drafts-header"
          onClick={() => setDraftsCollapsed((v) => !v)}
          aria-expanded={!draftsCollapsed}
        >
          <span className={`board__drafts-chevron ${draftsCollapsed ? "board__drafts-chevron--collapsed" : ""}`}>
            ▾
          </span>
          Drafts ({visibleDrafts.length})
        </button>
        {!draftsCollapsed && (
        <div className="board__drafts-list">
          {PRIORITY_QUADRANTS.map((q) => {
            const items = groupedDrafts[q] ?? [];
            if (items.length === 0) return null;
            return (
              <div key={q} className="board__quadrant">
                <h4 className={`board__quadrant-title board__quadrant-title--${quadrantClass(q)}`}>
                  {quadrantLabel(q)}
                </h4>
                <ul className="board__quadrant-list">
                  {items.map((t) => (
                    <TaskCard
                      key={t.id}
                      task={t}
                      projectName={t.project_id !== null ? projectNameById.get(t.project_id) : undefined}
                      pending={pending}
                      onOpenNotes={() => setNotesTask(t)}
                      onStatusChange={(status: TaskStatus) => patchTask(t.id, { status })}
                      onPriorityChange={(priority: string) => patchTask(t.id, { priority })}
                      onToggleToday={() => patchTask(t.id, { is_today: !t.is_today })}
                      onToggleThisWeek={() => patchTask(t.id, { is_this_week: !t.is_this_week })}
                      onDelete={() => handleDelete(t.id)}
                      onRelease={() => handleReleaseDraft(t.id)}
                    />
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
        )}
      </div>
    );
  }

  return (
    <section className="board" id="board">
      <div className="board__header">
        <h2>Tasks</h2>
        <button type="button" className="board__new-task" onClick={() => setShowNewTask(true)}>
          + Add task
        </button>
      </div>

      <div className="board__project-tabs">
        {projectTabs.length > 0 && (
          <>
            <button
              type="button"
              className={`board__project-tab ${selectedProjectId === null ? "board__project-tab--active" : ""}`}
              onClick={() => setSelectedProjectId(null)}
            >
              All
            </button>
            {projectTabs.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`board__project-tab ${selectedProjectId === p.id ? "board__project-tab--active" : ""}`}
                onClick={() => setSelectedProjectId(p.id)}
              >
                {p.name}
              </button>
            ))}
          </>
        )}
        <button
          type="button"
          className={`board__project-tab board__project-tab--sprint ${sprintOnly ? "board__project-tab--active" : ""}`}
          onClick={() => setSprintOnly((v) => !v)}
        >
          This Week
        </button>
      </div>

      {error && <p className="board__error">{error}</p>}

      {tasks === null && !error && <p className="board__loading">Loading…</p>}

      {tasks !== null && (
        <div className="board__columns">
          {renderColumn("today", "Today")}
          {renderColumn("pool", "Task Pool")}
        </div>
      )}

      {tasks !== null && visibleDrafts.length > 0 && renderDraftsSection()}

      {notesTask && (
        <NotesModal
          task={notesTask}
          tagTree={tagTree}
          projects={projects}
          onClose={() => setNotesTask(null)}
          onSaved={(updated) => {
            setTasks((prev) => prev?.map((t) => (t.id === updated.id ? updated : t)) ?? prev);
            refreshTags();
            onTasksChanged?.();
          }}
          onTagCreated={refreshTags}
        />
      )}

      {showNewTask && (
        <NewTaskModal
          tagTree={tagTree}
          projects={projects}
          onClose={() => setShowNewTask(false)}
          onCreated={(created) => {
            setTasks((prev) => (prev ? [...prev, created] : [created]));
            refreshTags();
            onTasksChanged?.();
          }}
          onTagCreated={refreshTags}
        />
      )}
    </section>
  );
}

export default Board;
