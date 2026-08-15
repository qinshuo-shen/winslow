import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { apiPost, ApiError } from "../../api/client";
import type { ProjectCreateRequest, ProjectOut, TagOut } from "../../api/types";
import { TagEditor } from "../Board/TagEditor";
import "../Board/TaskModal.css";

// Parallels NewTaskModal.tsx -- same overlay/panel shape (shares
// TaskModal.css wholesale) and the same TagEditor reused unmodified, since
// a Project is tagged exactly the way a task is (through the same shared
// tag pool, via the new project_tags join -- see procrastination_tool/projects.py).

interface NewProjectModalProps {
  tagTree: TagOut[];
  onClose: () => void;
  onCreated: (project: ProjectOut) => void;
  onTagCreated?: () => void;
}

export function NewProjectModal({ tagTree, onClose, onCreated, onTagCreated }: NewProjectModalProps) {
  const [name, setName] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    if (!name.trim()) {
      setError("Give the project a name first.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const body: ProjectCreateRequest = { name: name.trim(), notes, tags };
      const created = await apiPost<ProjectOut>("/projects", body);
      onCreated(created);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't create that project.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="task-modal__overlay" onClick={onClose}>
      <div className="task-modal" onClick={(e) => e.stopPropagation()}>
        <header className="task-modal__header">
          <h3>New project</h3>
          <button type="button" className="task-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {error && <p className="task-modal__error">{error}</p>}

        <div className="task-modal__fields">
          <input
            type="text"
            className="task-modal__field-name"
            placeholder="Project name…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={pending}
            autoFocus
          />
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

export default NewProjectModal;
