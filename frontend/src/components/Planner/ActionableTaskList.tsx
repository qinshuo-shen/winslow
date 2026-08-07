import type { TaskOut } from "../../api/types";
import "./ActionableTaskList.css";

// Mirrors app.py's `with st.expander(f"All actionable tasks ({len(all_tasks)})")`
// block: every actionable task (not just ones visible in today's pool),
// each with a "✓ Done" button that marks it Completed in Notion and
// deletes any calendar blocks tagged with it (POST /tasks/{page_id}/complete
// -- a real, semi-irreversible write, same as app.py's inline version).

interface ActionableTaskListProps {
  tasks: TaskOut[];
  completingPageId: string | null;
  onComplete: (pageId: string) => void;
}

export function ActionableTaskList({
  tasks,
  completingPageId,
  onComplete,
}: ActionableTaskListProps) {
  return (
    <details className="actionable-task-list">
      <summary>All actionable tasks ({tasks.length})</summary>
      {tasks.length === 0 && (
        <p className="actionable-task-list__empty">Nothing actionable in Notion right now.</p>
      )}
      {tasks.length > 0 && (
        <ul className="actionable-task-list__items">
          {tasks.map((t) => (
            <li key={t.page_id} className="actionable-task-list__item">
              <span className="actionable-task-list__label">
                <strong>{t.name}</strong> — {t.priority ?? "No priority"} — starts{" "}
                {t.start_date}
              </span>
              <button
                type="button"
                className="actionable-task-list__done-button"
                disabled={completingPageId === t.page_id}
                onClick={() => onComplete(t.page_id)}
              >
                {completingPageId === t.page_id ? "…" : "✓ Done"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

export default ActionableTaskList;
