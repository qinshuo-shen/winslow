import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { apiPatch, ApiError } from "../../api/client";
import type { BacklogTaskOut, BacklogTaskUpdateRequest, TagOut } from "../../api/types";
import { TagEditor } from "./TagEditor";
import "./TaskModal.css";

// Per-task Markdown note-taking (2.2 in the redesign plan) -- click a
// task's name on the Board to open this, edit raw Markdown in a textarea
// with a live rendered preview alongside, save via PATCH /api/backlog/{id}.
// No WYSIWYG editor -- this is a personal tool, a textarea + react-markdown
// preview is enough and keeps the dependency footprint tiny.
//
// Tags (same-day follow-up) share this modal rather than getting their own
// -- it's already the task's "detail view", same place Notion would put
// them. Shares TaskModal.css's overlay/panel styling with NewTaskModal.

interface NotesModalProps {
  task: BacklogTaskOut;
  tagTree: TagOut[];
  onClose: () => void;
  onSaved: (updated: BacklogTaskOut) => void;
  onTagCreated?: () => void;
}

export function NotesModal({ task, tagTree, onClose, onSaved, onTagCreated }: NotesModalProps) {
  const [notes, setNotes] = useState(task.notes);
  const [tags, setTags] = useState<string[]>(task.tags);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setPending(true);
    setError(null);
    try {
      const body: BacklogTaskUpdateRequest = { notes, tags };
      const updated = await apiPatch<BacklogTaskOut>(`/backlog/${task.id}`, body);
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save that note.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="task-modal__overlay" onClick={onClose}>
      <div className="task-modal" onClick={(e) => e.stopPropagation()}>
        <header className="task-modal__header">
          <h3>{task.name}</h3>
          <button type="button" className="task-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {error && <p className="task-modal__error">{error}</p>}

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
            placeholder="Write notes in Markdown…"
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
          <button type="button" className="task-modal__save" onClick={handleSave} disabled={pending}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export default NotesModal;
