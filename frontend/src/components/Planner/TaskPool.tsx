import { useDroppable } from "@dnd-kit/core";
import type { TaskOut } from "../../api/types";
import { DraggableTaskBox } from "./DraggableTaskBox";
import "./TaskPool.css";

// The task pool: a "+1" row (spawn an extra ephemeral instance of any
// actionable task, client-side only, matching app.py's plus_cols -- not
// filtered by the selected day, same as app.py) above a droppable box area
// showing one draggable instance per available slot for the selected day.
//
// Real per-instance identity via useDraggable({id}) (see DraggableTaskBox)
// is the concrete improvement over app.py/streamlit-sortables here: that
// implementation only round-tripped plain strings, so two instances of the
// same task name had to be disambiguated as "Task Name" / "Task Name (2)"
// just to stay unique within one sort_items() call. Every pool instance
// below gets a real unique id (`pool-${page_id}-${instanceIndex}`) and
// always renders the clean task name -- no disambiguation suffix, ever.

export interface PoolInstance {
  id: string;
  pageId: string;
  label: string;
}

interface TaskPoolProps {
  allTasks: TaskOut[];
  poolInstances: PoolInstance[];
  onPlusOne: (pageId: string) => void;
  dragDisabled?: boolean;
}

export function TaskPool({ allTasks, poolInstances, onPlusOne, dragDisabled }: TaskPoolProps) {
  // "pool-container" (not "pool") -- deliberately distinct from an active
  // pool item's own `{ type: "pool" }` drag payload (see Planner.tsx's
  // DragPayload union), so onDragEnd can tell "dropped ONTO the pool" apart
  // from "this is a pool-origin item" unambiguously.
  const { setNodeRef, isOver } = useDroppable({
    id: "pool",
    data: { type: "pool-container" },
  });

  return (
    <div className="task-pool-section">
      {allTasks.length > 0 && (
        <div className="task-pool__plus-row">
          <span className="task-pool__plus-caption">
            Need a task in more than one block? Add another copy of its box:
          </span>
          <div className="task-pool__plus-buttons">
            {allTasks.map((t) => (
              <button
                key={t.page_id}
                type="button"
                className="task-pool__plus-button"
                onClick={() => onPlusOne(t.page_id)}
              >
                +1 {t.name.slice(0, 24)}
              </button>
            ))}
          </div>
        </div>
      )}

      <div
        ref={setNodeRef}
        className={`task-pool${isOver ? " task-pool--over" : ""}`}
      >
        {poolInstances.length === 0 && (
          <p className="task-pool__empty">Nothing to drag onto this day yet.</p>
        )}
        {poolInstances.map((inst) => (
          <DraggableTaskBox
            key={inst.id}
            id={inst.id}
            label={inst.label}
            data={{ type: "pool", pageId: inst.pageId }}
            disabled={dragDisabled}
          />
        ))}
      </div>
    </div>
  );
}

export default TaskPool;
