import { useDroppable } from "@dnd-kit/core";
import type { RowStateOut } from "../../api/types";
import { DraggableTaskBox } from "./DraggableTaskBox";
import "./GridRow.css";

// One row = one useDroppable zone. "busy" rows are a plain, non-droppable
// locked line (matching app.py's 🔒 treatment -- not this tool's to
// reschedule). "assigned" rows are droppable-disabled (already occupied --
// a row only ever holds one task, mirroring app.py's "more than one task —
// drop rejected" rule, just enforced by not being a valid drop target at
// all rather than accepting the drop and then warning) but still render
// their occupant as its own draggable box, so it can be picked up and moved
// out (to the pool = unassign) or to another empty row. "empty" rows are a
// plain open droppable zone.

function formatHHMM(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

interface GridRowProps {
  index: number;
  rowState: RowStateOut;
  dragDisabled?: boolean;
}

export function GridRow({ index, rowState, dragDisabled }: GridRowProps) {
  const { row, status, event, busy_summary } = rowState;
  const timeLabel = `${formatHHMM(row.start)}–${formatHHMM(row.work_end)}`;

  const { setNodeRef, isOver } = useDroppable({
    id: `row-${index}`,
    data: { type: "row", row },
    disabled: status !== "empty",
  });

  if (status === "busy") {
    return (
      <div className="grid-row grid-row--busy">
        <span className="grid-row__time">🔒 {timeLabel}</span>
        <span className="grid-row__busy-summary">busy ({busy_summary})</span>
      </div>
    );
  }

  return (
    <div
      ref={setNodeRef}
      className={`grid-row${status === "empty" ? " grid-row--empty" : " grid-row--assigned"}${
        isOver ? " grid-row--over" : ""
      }`}
    >
      <span className="grid-row__time">{timeLabel}</span>
      <div className="grid-row__slot">
        {status === "assigned" && event && (
          <DraggableTaskBox
            id={event.uid}
            label={event.summary}
            data={{ type: "assigned", uid: event.uid }}
            disabled={dragDisabled}
          />
        )}
      </div>
    </div>
  );
}

export default GridRow;
