import type { CSSProperties } from "react";
import { useDraggable } from "@dnd-kit/core";
import "./DraggableTaskBox.css";

// Shared visual for both pool items and assigned-row items. Real object
// identity per box comes from `id` + `data` (dnd-kit), not from the label --
// a genuine improvement over the old streamlit-sortables implementation,
// which only round-tripped plain strings and had to invent "Task Name (2)"
// disambiguation suffixes to keep duplicate task names unique within one
// sort_items() call. Here the label is always just the clean task name.

interface DraggableTaskBoxProps {
  id: string;
  label: string;
  data?: Record<string, unknown>;
  disabled?: boolean;
}

export function DraggableTaskBox({ id, label, data, disabled }: DraggableTaskBoxProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id,
    data,
    disabled,
  });

  const style: CSSProperties | undefined = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
      }
    : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`draggable-task-box${isDragging ? " draggable-task-box--dragging" : ""}`}
      {...listeners}
      {...attributes}
    >
      {label}
    </div>
  );
}

export default DraggableTaskBox;
