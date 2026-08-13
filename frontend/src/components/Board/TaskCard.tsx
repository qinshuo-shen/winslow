import { PRIORITY_QUADRANTS, TASK_STATUSES, quadrantLabel } from "../../api/types";
import type { BacklogTaskOut, TaskStatus } from "../../api/types";
import { quadrantClass } from "./quadrantStyle";

interface TaskCardProps {
  task: BacklogTaskOut;
  pending: boolean;
  onOpenNotes: () => void;
  onStatusChange: (status: TaskStatus) => void;
  onPriorityChange: (priority: string) => void;
  onToggleToday: () => void;
  onToggleThisWeek: () => void;
  onDelete: () => void;
}

export function TaskCard({
  task,
  pending,
  onOpenNotes,
  onStatusChange,
  onPriorityChange,
  onToggleToday,
  onToggleThisWeek,
  onDelete,
}: TaskCardProps) {
  return (
    <li className={`board-card board-card--${quadrantClass(task.priority)}`}>
      <div className="board-card__row">
        <button type="button" className="board-card__name" onClick={onOpenNotes}>
          {task.name}
          {task.notes.trim() && <span className="board-card__notes-dot" title="Has notes" />}
        </button>
        <button
          type="button"
          className="board-card__remove"
          disabled={pending}
          onClick={onDelete}
          aria-label={`Remove ${task.name}`}
        >
          ×
        </button>
      </div>

      {task.carried_forward && (
        <span className="board-card__carried-forward" title="Still in progress -- carried forward from yesterday">
          continuing from yesterday
        </span>
      )}

      {task.is_current_week_commitment && (
        <span className="board-card__this-week" title="Committed to this week's sprint">
          this week
        </span>
      )}

      {task.specific_project && (
        <span className="board-card__project">{task.specific_project}</span>
      )}

      {task.tags.length > 0 && (
        <div className="board-card__tags">
          {task.tags.map((t) => (
            <span key={t} className="board-card__tag">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="board-card__row board-card__row--controls">
        <div className={`board-card__priority-badge board-card__priority-badge--${quadrantClass(task.priority)}`}>
          <select
            className="board-card__priority"
            value={task.priority}
            disabled={pending}
            onChange={(e) => onPriorityChange(e.target.value)}
          >
            {PRIORITY_QUADRANTS.map((q) => (
              <option key={q} value={q}>
                {quadrantLabel(q)}
              </option>
            ))}
          </select>
        </div>
        <div className={`board-card__status-badge board-card__status-badge--${task.status}`}>
          <select
            className="board-card__status"
            value={task.status}
            disabled={pending}
            onChange={(e) => onStatusChange(e.target.value as TaskStatus)}
          >
            {TASK_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="board-card__move"
          disabled={pending}
          onClick={onToggleToday}
        >
          {task.is_today ? "→ Pool" : "→ Today"}
        </button>
        <button
          type="button"
          className="board-card__week-toggle"
          disabled={pending}
          onClick={onToggleThisWeek}
        >
          {task.is_this_week ? "− This Week" : "+ This Week"}
        </button>
      </div>
    </li>
  );
}

export default TaskCard;
