import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiGet, apiPatch, ApiError } from "../../api/client";
import { PRIORITY_QUADRANTS, quadrantLabel } from "../../api/types";
import type { BacklogTaskOut, BacklogTaskUpdateRequest, TagOut, TaskStatus } from "../../api/types";
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
// Project filter tabs (fourth same-day follow-up): the tag hierarchy's
// top-level tags ("PhD core", "Education", ...) double as a filter bar
// above the columns -- selecting one shows only tasks carrying that
// project tag or one of its sub-tags; "All" (default) shows everything.

interface BoardProps {
  onTasksChanged?: () => void;
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

export function Board({ onTasksChanged }: BoardProps) {
  const [tasks, setTasks] = useState<BacklogTaskOut[] | null>(null);
  const [tagTree, setTagTree] = useState<TagOut[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [notesTask, setNotesTask] = useState<BacklogTaskOut | null>(null);
  const [showNewTask, setShowNewTask] = useState(false);

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

  useEffect(() => {
    refresh();
    refreshTags();
  }, []);

  const topLevelProjects = useMemo(
    () => tagTree.filter((t) => t.parent === null).map((t) => t.name).sort(),
    [tagTree],
  );

  // A project's own name plus every sub-tag nested under it -- a task
  // matches this project tab if any of its tags fall in this set.
  const projectSubtree = useMemo(() => {
    if (!selectedProject) return null;
    const names = new Set<string>([selectedProject]);
    for (const t of tagTree) {
      if (t.parent === selectedProject) names.add(t.name);
    }
    return names;
  }, [tagTree, selectedProject]);

  // Done tasks never appear on the Board -- they're historical record at
  // that point (especially post-Notion-migration, where completed tasks
  // badly outnumber open ones), not something to work from day to day.
  // Nothing is deleted, just excluded from this view; the evaluation
  // report's "tasks completed today" still counts them via completed_at.
  const visibleTasks = useMemo(() => {
    const notDone = (tasks ?? []).filter((t) => t.status !== "completed");
    if (!projectSubtree) return notDone;
    return notDone.filter((t) => t.tags.some((tag) => projectSubtree.has(tag)));
  }, [tasks, projectSubtree]);
  const grouped = useMemo(() => groupByQuadrant(visibleTasks), [visibleTasks]);

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
                      pending={pending}
                      onOpenNotes={() => setNotesTask(t)}
                      onStatusChange={(status: TaskStatus) => patchTask(t.id, { status })}
                      onPriorityChange={(priority: string) => patchTask(t.id, { priority })}
                      onToggleToday={() => patchTask(t.id, { is_today: !t.is_today })}
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

  return (
    <section className="board">
      <div className="board__header">
        <h2>Tasks</h2>
        <button type="button" className="board__new-task" onClick={() => setShowNewTask(true)}>
          + Add task
        </button>
      </div>

      {topLevelProjects.length > 0 && (
        <div className="board__project-tabs">
          <button
            type="button"
            className={`board__project-tab ${selectedProject === null ? "board__project-tab--active" : ""}`}
            onClick={() => setSelectedProject(null)}
          >
            All
          </button>
          {topLevelProjects.map((p) => (
            <button
              key={p}
              type="button"
              className={`board__project-tab ${selectedProject === p ? "board__project-tab--active" : ""}`}
              onClick={() => setSelectedProject(p)}
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {error && <p className="board__error">{error}</p>}

      {tasks === null && !error && <p className="board__loading">Loading…</p>}

      {tasks !== null && (
        <div className="board__columns">
          {renderColumn("today", "Today")}
          {renderColumn("pool", "Task Pool")}
        </div>
      )}

      {notesTask && (
        <NotesModal
          task={notesTask}
          tagTree={tagTree}
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
