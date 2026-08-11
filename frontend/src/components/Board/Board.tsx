import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "../../api/client";
import { PRIORITY_QUADRANTS, quadrantLabel } from "../../api/types";
import type { BacklogTaskOut, BacklogTaskUpdateRequest, TaskStatus } from "../../api/types";
import { TaskCard } from "./TaskCard";
import { NotesModal } from "./NotesModal";
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
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [notesTask, setNotesTask] = useState<BacklogTaskOut | null>(null);

  const [name, setName] = useState("");
  // Referenced by literal string, not array index -- PRIORITY_QUADRANTS's
  // order is just display order (see types.ts) and shouldn't silently
  // change which quadrant a new task defaults into if that order changes.
  const [priority, setPriority] = useState<string>("Quick Wins (High Impact-Low Effort)");
  const [project, setProject] = useState("");

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
      setAvailableTags(await apiGet<string[]>("/tags"));
    } catch {
      // Non-critical -- the tag editor just falls back to no suggestions.
    }
  }

  useEffect(() => {
    refresh();
    refreshTags();
  }, []);

  // Done tasks never appear on the Board -- they're historical record at
  // that point (especially post-Notion-migration, where completed tasks
  // badly outnumber open ones), not something to work from day to day.
  // Nothing is deleted, just excluded from this view; the evaluation
  // report's "tasks completed today" still counts them via completed_at.
  const visibleTasks = useMemo(
    () => (tasks ?? []).filter((t) => t.status !== "completed"),
    [tasks],
  );
  const grouped = useMemo(() => groupByQuadrant(visibleTasks), [visibleTasks]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setPending(true);
    setError(null);
    try {
      await apiPost("/backlog", {
        name: name.trim(),
        priority,
        specific_project: project.trim() || null,
      });
      setName("");
      setProject("");
      await refresh();
      onTasksChanged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't add that task.");
    } finally {
      setPending(false);
    }
  }

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
    );
  }

  return (
    <section className="board">
      <h2>Tasks</h2>

      <form className="board__add-form" onSubmit={handleAdd}>
        <input
          type="text"
          placeholder="Add a task…"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={pending}
        />
        <select value={priority} onChange={(e) => setPriority(e.target.value)} disabled={pending}>
          {PRIORITY_QUADRANTS.map((q) => (
            <option key={q} value={q}>
              {quadrantLabel(q)}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Project (optional)"
          value={project}
          onChange={(e) => setProject(e.target.value)}
          disabled={pending}
          className="board__add-form-project"
        />
        <button type="submit" disabled={pending || !name.trim()}>
          Add
        </button>
      </form>

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
          availableTags={availableTags}
          onClose={() => setNotesTask(null)}
          onSaved={(updated) => {
            setTasks((prev) => prev?.map((t) => (t.id === updated.id ? updated : t)) ?? prev);
            refreshTags();
            onTasksChanged?.();
          }}
        />
      )}
    </section>
  );
}

export default Board;
