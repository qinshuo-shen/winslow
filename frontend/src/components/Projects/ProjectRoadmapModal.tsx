import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { apiGet, apiPatch, apiPost, ApiError } from "../../api/client";
import { PRIORITY_QUADRANTS, TASK_STATUSES, quadrantLabel } from "../../api/types";
import type {
  BacklogTaskCreateRequest,
  BacklogTaskOut,
  BacklogTaskUpdateRequest,
  ProjectOut,
  ProjectUpdateRequest,
  TagOut,
  TaskStatus,
} from "../../api/types";
import { NotesModal } from "../Board/NotesModal";
import { TagEditor } from "../Board/TagEditor";
import "../Board/TaskModal.css";
import "./Projects.css";

// The roadmap popup (Page 2's central new UI piece): an edit section
// (mirrors NotesModal.tsx's own layout) above a vertical milestone
// timeline of the project's breakdown tasks -- chosen over a Kanban/mini-
// Board layout, confirmed with the user directly. Tasks list top-to-bottom
// in creation order (see procrastination_tool.tasks.list_tasks_for_project),
// each showing its current status; clicking a task name reuses the
// existing NotesModal unmodified for full notes/tags editing rather than
// building a second editor. The footer quick-add is the primary top-down
// way to grow a project (name + quadrant, no nested modal/second overlay
// stacked on this one) -- deliberately not gated behind opening yet
// another dialog, per this app's own documented stance against
// reintroducing friction/decision points.

interface ProjectRoadmapModalProps {
  project: ProjectOut;
  tagTree: TagOut[];
  onClose: () => void;
  onSaved: (updated: ProjectOut) => void;
  onTagCreated?: () => void;
}

export function ProjectRoadmapModal({
  project,
  tagTree,
  onClose,
  onSaved,
  onTagCreated,
}: ProjectRoadmapModalProps) {
  const [name, setName] = useState(project.name);
  const [status, setStatus] = useState<TaskStatus>(project.status as TaskStatus);
  const [tags, setTags] = useState<string[]>(project.tags);
  const [notes, setNotes] = useState(project.notes);
  const [savePending, setSavePending] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [steps, setSteps] = useState<BacklogTaskOut[] | null>(null);
  const [stepsError, setStepsError] = useState<string | null>(null);
  const [notesTask, setNotesTask] = useState<BacklogTaskOut | null>(null);

  const [newStepName, setNewStepName] = useState("");
  const [newStepPriority, setNewStepPriority] = useState<string>(PRIORITY_QUADRANTS[0]);
  const [addPending, setAddPending] = useState(false);

  async function refreshSteps() {
    try {
      const data = await apiGet<BacklogTaskOut[]>(`/projects/${project.id}/tasks`);
      setSteps(data);
    } catch (e) {
      setStepsError(e instanceof ApiError ? e.message : "Couldn't load this project's tasks.");
    }
  }

  useEffect(() => {
    refreshSteps();
    // Only re-fetch if the user opens a different project while this modal
    // type is reused across cards -- project.id is the real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  async function handleSave() {
    if (!name.trim()) {
      setSaveError("Give the project a name first.");
      return;
    }
    setSavePending(true);
    setSaveError(null);
    try {
      const body: ProjectUpdateRequest = { name: name.trim(), status, notes, tags };
      const updated = await apiPatch<ProjectOut>(`/projects/${project.id}`, body);
      onSaved(updated);
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : "Couldn't save this project.");
    } finally {
      setSavePending(false);
    }
  }

  async function handleStepStatusChange(step: BacklogTaskOut, newStatus: TaskStatus) {
    try {
      const body: BacklogTaskUpdateRequest = { status: newStatus };
      const updated = await apiPatch<BacklogTaskOut>(`/backlog/${step.id}`, body);
      setSteps((prev) => prev?.map((s) => (s.id === step.id ? updated : s)) ?? prev);
    } catch (e) {
      setStepsError(e instanceof ApiError ? e.message : "Couldn't update that task.");
    }
  }

  async function handleAddStep() {
    if (!newStepName.trim()) return;
    setAddPending(true);
    setStepsError(null);
    try {
      const body: BacklogTaskCreateRequest = {
        name: newStepName.trim(),
        priority: newStepPriority,
        project_id: project.id,
      };
      const created = await apiPost<BacklogTaskOut>("/backlog", body);
      setSteps((prev) => (prev ? [...prev, created] : [created]));
      setNewStepName("");
    } catch (e) {
      setStepsError(e instanceof ApiError ? e.message : "Couldn't add that task.");
    } finally {
      setAddPending(false);
    }
  }

  return (
    <>
    <div className="task-modal__overlay" onClick={onClose}>
      <div className="task-modal project-roadmap-modal" onClick={(e) => e.stopPropagation()}>
        <header className="task-modal__header">
          <h3>{project.name}</h3>
          <button type="button" className="task-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {saveError && <p className="task-modal__error">{saveError}</p>}

        <div className="task-modal__fields">
          <input
            type="text"
            className="task-modal__field-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={savePending}
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as TaskStatus)}
            disabled={savePending}
          >
            {TASK_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <TagEditor
          tags={tags}
          tagTree={tagTree}
          onChange={setTags}
          onTagCreated={onTagCreated}
          disabled={savePending}
        />

        <div className="task-modal__panes project-roadmap-modal__notes-panes">
          <textarea
            className="task-modal__editor"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Write notes in Markdown… (optional)"
            disabled={savePending}
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
          <button type="button" className="task-modal__save" onClick={handleSave} disabled={savePending}>
            {savePending ? "Saving…" : "Save changes"}
          </button>
        </div>

        <div className="project-roadmap-modal__timeline-section">
          <h4 className="project-roadmap-modal__timeline-title">Roadmap</h4>

          {stepsError && <p className="task-modal__error">{stepsError}</p>}

          {steps === null && !stepsError && <p className="board__loading">Loading…</p>}

          {steps !== null && steps.length === 0 && (
            <p className="project-roadmap-modal__timeline-empty">
              No steps yet -- add the first one below.
            </p>
          )}

          {steps !== null && steps.length > 0 && (
            <ol className="project-roadmap-modal__timeline">
              {steps.map((step) => (
                <li key={step.id} className={`project-roadmap-modal__step project-roadmap-modal__step--${step.status}`}>
                  <span className="project-roadmap-modal__step-dot" aria-hidden="true" />
                  <button
                    type="button"
                    className="project-roadmap-modal__step-name"
                    onClick={() => setNotesTask(step)}
                  >
                    {step.name}
                  </button>
                  <select
                    className="project-roadmap-modal__step-status"
                    value={step.status}
                    onChange={(e) => handleStepStatusChange(step, e.target.value as TaskStatus)}
                  >
                    {TASK_STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </li>
              ))}
            </ol>
          )}

          <div className="project-roadmap-modal__quick-add">
            <input
              type="text"
              placeholder="Add a step…"
              value={newStepName}
              onChange={(e) => setNewStepName(e.target.value)}
              disabled={addPending}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddStep();
                }
              }}
            />
            <select
              value={newStepPriority}
              onChange={(e) => setNewStepPriority(e.target.value)}
              disabled={addPending}
            >
              {PRIORITY_QUADRANTS.map((q) => (
                <option key={q} value={q}>
                  {quadrantLabel(q)}
                </option>
              ))}
            </select>
            <button type="button" onClick={handleAddStep} disabled={addPending || !newStepName.trim()}>
              Add
            </button>
          </div>
        </div>
      </div>
    </div>

    {/* Rendered as a sibling of the roadmap overlay above, not nested
        inside it -- NotesModal has its own full-screen overlay/onClose, and
        nesting it would let a backdrop click bubble up through the
        roadmap's own overlay onClick and close both modals at once. */}
    {notesTask && (
      <NotesModal
        task={notesTask}
        tagTree={tagTree}
        onClose={() => setNotesTask(null)}
        onSaved={(updated) => {
          setSteps((prev) => prev?.map((s) => (s.id === updated.id ? updated : s)) ?? prev);
          onTagCreated?.();
        }}
        onTagCreated={onTagCreated}
      />
    )}
    </>
  );
}

export default ProjectRoadmapModal;
