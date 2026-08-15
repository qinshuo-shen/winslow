import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { apiPost, ApiError } from "../../api/client";
import { PRIORITY_QUADRANTS, quadrantLabel } from "../../api/types";
import type { BacklogTaskCreateRequest, BacklogTaskOut, ProjectOut, TagOut } from "../../api/types";
import { TagEditor } from "./TagEditor";
import "./TaskModal.css";

// Single "+ Add task" entry point (replaces the old always-visible
// three-field inline form) -- name, quadrant, tags, and Markdown notes are
// all set up front in one place instead of adding a bare task then
// separately opening NotesModal to attach notes/tags. Shares TaskModal.css
// and its overlay/panel shape with NotesModal (the same modal used to
// edit an existing task's notes/tags after creation).
//
// 2026-08 page-split redesign: an optional "Linked project" picker (the
// bottom-up half of task<->Project assignment -- the primary, top-down
// half is the roadmap popup's own quick-add, see ProjectRoadmapModal.tsx).
// Deliberately a separate control from the "Project (optional)" free-text
// field above and from TagEditor's own "Project (optional)…" tag picker --
// three unrelated concepts (specific_project legacy string, the tag
// Project/sub-project hierarchy, and a real linked Project entity) that
// happen to share the word "Project."

interface NewTaskModalProps {
  tagTree: TagOut[];
  projects: ProjectOut[];
  onClose: () => void;
  onCreated: (task: BacklogTaskOut) => void;
  onTagCreated?: () => void;
}

export function NewTaskModal({ tagTree, projects, onClose, onCreated, onTagCreated }: NewTaskModalProps) {
  const [name, setName] = useState("");
  const [priority, setPriority] = useState<string>("Quick Wins (High Impact-Low Effort)");
  const [project, setProject] = useState("");
  const [linkedProjectId, setLinkedProjectId] = useState<string>("");
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    if (!name.trim()) {
      setError("Give the task a name first.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const body: BacklogTaskCreateRequest = {
        name: name.trim(),
        priority,
        notes,
        specific_project: project.trim() || null,
        tags,
        project_id: linkedProjectId ? Number(linkedProjectId) : null,
      };
      const created = await apiPost<BacklogTaskOut>("/backlog", body);
      onCreated(created);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't create that task.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="task-modal__overlay" onClick={onClose}>
      <div className="task-modal" onClick={(e) => e.stopPropagation()}>
        <header className="task-modal__header">
          <h3>New task</h3>
          <button type="button" className="task-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {error && <p className="task-modal__error">{error}</p>}

        <div className="task-modal__fields">
          <input
            type="text"
            className="task-modal__field-name"
            placeholder="Task name…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={pending}
            autoFocus
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
          />
          <select
            value={linkedProjectId}
            onChange={(e) => setLinkedProjectId(e.target.value)}
            disabled={pending}
            aria-label="Linked project"
          >
            <option value="">Linked project (optional)…</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        <TagEditor
          tags={tags}
          tagTree={tagTree}
          onChange={setTags}
          onTagCreated={onTagCreated}
          disabled={pending}
        />

        <div className="task-modal__panes">
          <textarea
            className="task-modal__editor"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Write notes in Markdown… (optional)"
            disabled={pending}
          />
          <div className="task-modal__preview">
            {notes.trim() ? (
              <ReactMarkdown>{notes}</ReactMarkdown>
            ) : (
              <p className="task-modal__preview-empty">Preview appears here.</p>
            )}
          </div>
        </div>

        <div className="task-modal__actions">
          <button type="button" onClick={onClose} disabled={pending}>
            Cancel
          </button>
          <button type="button" className="task-modal__save" onClick={handleCreate} disabled={pending}>
            Create
          </button>
        </div>
      </div>
    </div>
  );
}

export default NewTaskModal;
