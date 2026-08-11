import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, ApiError } from "../../api/client";
import { PRIORITY_QUADRANTS, quadrantLabel } from "../../api/types";
import type { BacklogTaskOut } from "../../api/types";
import "./TaskInput.css";

// The native task backlog (2026-08-11 redesign) -- replaces the old
// Notion-synced task list. Adding a task means placing it directly into one
// quadrant of the Impact/Effort priority matrix; there's no separate
// "assign a priority later" step, since proactive_scheduler.py needs a
// quadrant to rank against from the moment a task exists.

interface TaskInputProps {
  onTasksChanged?: () => void;
}

export function TaskInput({ onTasksChanged }: TaskInputProps) {
  const [tasks, setTasks] = useState<BacklogTaskOut[] | null>(null);
  const [name, setName] = useState("");
  const [priority, setPriority] = useState<string>(PRIORITY_QUADRANTS[2]); // Quick Wins default
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function refresh() {
    try {
      const data = await apiGet<BacklogTaskOut[]>("/backlog");
      setTasks(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your task list.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setPending(true);
    setError(null);
    try {
      await apiPost("/backlog", { name: name.trim(), priority });
      setName("");
      await refresh();
      onTasksChanged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't add that task.");
    } finally {
      setPending(false);
    }
  }

  async function handleRemove(id: number) {
    setPending(true);
    setError(null);
    try {
      await apiDelete(`/backlog/${id}`);
      await refresh();
      onTasksChanged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove that task.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="task-input">
      <h2>What's on your plate</h2>

      <form className="task-input__form" onSubmit={handleAdd}>
        <input
          type="text"
          placeholder="Add a task…"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={pending}
        />
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          disabled={pending}
        >
          {PRIORITY_QUADRANTS.map((q) => (
            <option key={q} value={q}>
              {quadrantLabel(q)}
            </option>
          ))}
        </select>
        <button type="submit" disabled={pending || !name.trim()}>
          Add
        </button>
      </form>

      {error && <p className="task-input__error">{error}</p>}

      {tasks !== null && tasks.length === 0 && (
        <p className="task-input__empty">Nothing queued yet -- add something above.</p>
      )}

      {tasks !== null && tasks.length > 0 && (
        <ul className="task-input__list">
          {tasks.map((t) => (
            <li key={t.id} className="task-input__item">
              <span className="task-input__item-quadrant">{quadrantLabel(t.priority)}</span>
              <span className="task-input__item-name">{t.name}</span>
              <button
                type="button"
                className="task-input__remove"
                disabled={pending}
                onClick={() => handleRemove(t.id)}
                aria-label={`Remove ${t.name}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default TaskInput;
