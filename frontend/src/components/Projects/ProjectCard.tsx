import { TASK_STATUSES } from "../../api/types";
import type { ProjectOut } from "../../api/types";

interface ProjectCardProps {
  project: ProjectOut;
  pending: boolean;
  onOpen: () => void;
  onDelete: () => void;
}

export function ProjectCard({ project, pending, onOpen, onDelete }: ProjectCardProps) {
  const statusLabel = TASK_STATUSES.find((s) => s.value === project.status)?.label ?? project.status;

  return (
    <li className="board-card board-card--project">
      <div className="board-card__row">
        <button type="button" className="board-card__name" onClick={onOpen}>
          {project.name}
          {project.notes.trim() && <span className="board-card__notes-dot" title="Has notes" />}
        </button>
        <button
          type="button"
          className="board-card__remove"
          disabled={pending}
          onClick={onDelete}
          aria-label={`Remove ${project.name}`}
          title="Remove project (tasks stay, just unlinked)"
        >
          ×
        </button>
      </div>

      {project.tags.length > 0 && (
        <div className="board-card__tags">
          {project.tags.map((t) => (
            <span key={t} className="board-card__tag">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="board-card__row board-card__row--controls">
        <div className={`board-card__status-badge board-card__status-badge--${project.status}`}>
          <span className="project-card__status-label">{statusLabel}</span>
        </div>
      </div>
    </li>
  );
}

export default ProjectCard;
