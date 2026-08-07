import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import { apiDelete, apiGet, apiPost, ApiError } from "../../api/client";
import type {
  AssignedEventOut,
  AssignRequest,
  CompleteTaskOut,
  DeleteAssignOut,
  GridOut,
  MoveRequest,
  PlannerRefreshOut,
  RowOut,
  TaskOut,
  WeekRangeOut,
} from "../../api/types";
import { ActionableTaskList } from "./ActionableTaskList";
import { ConflictCheckButton } from "./ConflictCheckButton";
import { DaySelector } from "./DaySelector";
import { DraggableTaskBox } from "./DraggableTaskBox";
import { GridRow } from "./GridRow";
import { TaskPool } from "./TaskPool";
import type { PoolInstance } from "./TaskPool";
import "./Planner.css";

// Top-level orchestration for "🗓️ Plan your week" -- app.py's feature
// logic (pool/instance model, conflict-check opt-in, Done/Refresh behavior)
// replicated exactly, but with IMMEDIATE writes per drag instead of
// app.py's local-first/pending-state/Submit-button model (that batching was
// purely a Streamlit-rerun-cost workaround that doesn't apply here -- the
// user explicitly decided writes should happen immediately, confirmed in
// this phase's plan). Every assign/move/unassign/complete/refresh action
// below is a REAL, IMMEDIATE Calendar.app (and, for complete, Notion) write.
//
// Owns ONE shared @dnd-kit DndContext for the currently-visible day's grid
// -- only one day is ever mounted at a time (see DaySelector's docstring
// for why, mirroring app.py's st.radio-over-st.tabs reasoning).

type DragPayload =
  | { type: "pool"; pageId: string }
  | { type: "assigned"; uid: string }
  | { type: "row"; row: RowOut }
  | { type: "pool-container" };

function isDay(candidate: string, day: string): boolean {
  return candidate <= day;
}

export function Planner() {
  const [weekRange, setWeekRange] = useState<WeekRangeOut | null>(null);
  const [weekRangeError, setWeekRangeError] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const [tasks, setTasks] = useState<TaskOut[] | null>(null);
  const [tasksError, setTasksError] = useState<string | null>(null);

  const [grid, setGrid] = useState<GridOut | null>(null);
  const [gridError, setGridError] = useState<string | null>(null);

  const [extraInstances, setExtraInstances] = useState<Record<string, number>>({});
  const conflictCheckedDaysRef = useRef<Set<string>>(new Set());
  const [conflictVersion, setConflictVersion] = useState(0); // bumps to re-render on ref mutation

  const [checkingConflicts, setCheckingConflicts] = useState(false);
  const [dragBusy, setDragBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [completingPageId, setCompletingPageId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshLog, setRefreshLog] = useState<PlannerRefreshOut | null>(null);

  const [activeDragLabel, setActiveDragLabel] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  // --- initial week-range fetch -----------------------------------------
  useEffect(() => {
    let cancelled = false;
    apiGet<WeekRangeOut>("/planner/week-range")
      .then((data) => {
        if (cancelled) return;
        setWeekRange(data);
        setSelectedDay(data.today);
      })
      .catch((e: ApiError) => {
        if (!cancelled) setWeekRangeError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const data = await apiGet<TaskOut[]>("/tasks");
      setTasks(data);
      setTasksError(null);
    } catch (e) {
      setTasksError(e instanceof ApiError ? e.message : "Failed to load tasks.");
    }
  }, []);

  const fetchGrid = useCallback(async (day: string) => {
    const checkConflicts = conflictCheckedDaysRef.current.has(day);
    try {
      const data = await apiGet<GridOut>(
        `/planner/grid/${day}?check_conflicts=${checkConflicts}`,
      );
      setGrid(data);
      setGridError(null);
    } catch (e) {
      setGridError(e instanceof ApiError ? e.message : "Failed to load the day's grid.");
    }
  }, []);

  // --- initial task-list fetch (once) -------------------------------------
  // Tasks are day-independent -- poolInstances (below) already filters them
  // client-side by start_date -- only the grid actually varies per day.
  // Re-fetching the whole task list (a live Notion round trip) on every
  // day-tab click was pure wasted latency; tasks stay fresh after write
  // actions via refetchDay() instead (assign/move/unassign/complete/refresh
  // all call it), so a once-per-mount fetch here is sufficient.
  useEffect(() => {
    if (!selectedDay || tasks !== null) return;
    fetchTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDay]);

  // --- fetch the grid whenever the selected day changes -------------------
  useEffect(() => {
    if (!selectedDay) return;
    setGrid(null);
    fetchGrid(selectedDay);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDay]);

  const refetchDay = useCallback(async () => {
    if (!selectedDay) return;
    await Promise.all([fetchTasks(), fetchGrid(selectedDay)]);
  }, [selectedDay, fetchTasks, fetchGrid]);

  async function handleCheckConflicts() {
    if (!selectedDay) return;
    setCheckingConflicts(true);
    setGridError(null);
    try {
      const data = await apiGet<GridOut>(`/planner/grid/${selectedDay}?check_conflicts=true`);
      conflictCheckedDaysRef.current.add(selectedDay);
      setConflictVersion((v) => v + 1);
      setGrid(data);
    } catch (e) {
      setGridError(e instanceof ApiError ? e.message : "Failed to check conflicts.");
    } finally {
      setCheckingConflicts(false);
    }
  }

  function handlePlusOne(pageId: string) {
    setExtraInstances((prev) => ({ ...prev, [pageId]: (prev[pageId] ?? 0) + 1 }));
  }

  async function handleComplete(pageId: string) {
    setCompletingPageId(pageId);
    setActionError(null);
    try {
      await apiPost<CompleteTaskOut>(`/tasks/${pageId}/complete`);
      await refetchDay();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Failed to complete task.");
    } finally {
      setCompletingPageId(null);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    setActionError(null);
    try {
      const result = await apiPost<PlannerRefreshOut>("/planner/refresh");
      setRefreshLog(result);
      await refetchDay();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Failed to refresh.");
    } finally {
      setRefreshing(false);
    }
  }

  function handleDragStart(event: DragStartEvent) {
    const data = event.active.data.current as DragPayload | undefined;
    if (data?.type === "pool") {
      const inst = poolInstances.find((i) => i.id === event.active.id);
      setActiveDragLabel(inst?.label ?? null);
    } else if (data?.type === "assigned") {
      const row = grid?.rows.find((r) => r.event?.uid === data.uid);
      setActiveDragLabel(row?.event?.summary ?? null);
    }
  }

  async function handleDragEnd(dragEvent: DragEndEvent) {
    setActiveDragLabel(null);
    // Belt-and-suspenders alongside the disabled={dragBusy} threaded into
    // TaskPool/GridRow's draggables below: those prevent a *new* drag from
    // starting while a previous write is in flight, but can't stop a drag
    // that had already started (pointer already captured) from completing
    // mid-write. Bailing out here means a drop that lands while dragBusy is
    // still true is simply ignored -- no second concurrent write is ever
    // issued, and the dropped item just snaps back since no state changes.
    if (dragBusy) return;
    const { active, over } = dragEvent;
    if (!over || !selectedDay) return;

    const activeData = active.data.current as DragPayload | undefined;
    const overData = over.data.current as DragPayload | undefined;
    if (!activeData || !overData) return;

    try {
      if (activeData.type === "pool" && overData.type === "row") {
        setDragBusy(true);
        const body: AssignRequest = {
          page_id: activeData.pageId,
          day: selectedDay,
          row_start: overData.row.start,
          row_end: overData.row.work_end,
        };
        await apiPost<AssignedEventOut>("/planner/assign", body);
        await refetchDay();
      } else if (activeData.type === "assigned" && overData.type === "pool-container") {
        setDragBusy(true);
        await apiDelete<DeleteAssignOut>(`/planner/assign/${activeData.uid}`);
        await refetchDay();
      } else if (activeData.type === "assigned" && overData.type === "row") {
        setDragBusy(true);
        const body: MoveRequest = {
          uid: activeData.uid,
          day: selectedDay,
          row_start: overData.row.start,
          row_end: overData.row.work_end,
        };
        await apiPost<AssignedEventOut>("/planner/move", body);
        await refetchDay();
      }
      setActionError(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Drag action failed.");
    } finally {
      setDragBusy(false);
    }
  }

  // --- pool instance computation (mirrors app.py exactly) -----------------
  // available = 1 + extra_instances[page_id] - assigned_count (assigned_count
  // is GLOBAL, any day -- see TaskOut.assigned_count / block_grid.
  // count_assigned_instances), and a task only appears once its own
  // start_date has arrived as of the day being planned.
  const poolInstances: PoolInstance[] = useMemo(() => {
    if (!tasks || !selectedDay) return [];
    const out: PoolInstance[] = [];
    for (const t of tasks) {
      if (!isDay(t.start_date, selectedDay)) continue;
      const available = 1 + (extraInstances[t.page_id] ?? 0) - t.assigned_count;
      for (let i = 0; i < Math.max(0, available); i++) {
        out.push({ id: `pool-${t.page_id}-${i}`, pageId: t.page_id, label: t.name });
      }
    }
    return out;
  }, [tasks, selectedDay, extraInstances]);

  const busyRowCount = grid ? grid.rows.filter((r) => r.status === "busy").length : null;
  // `conflictVersion` isn't read for its value -- it's a dependency that
  // forces this render to re-run after conflictCheckedDaysRef.current (a
  // plain ref, so mutating it alone doesn't trigger React) gains a new day.
  void conflictVersion;
  const conflictsChecked = selectedDay ? conflictCheckedDaysRef.current.has(selectedDay) : false;

  return (
    <section className="planner">
      <div className="planner__header-row">
        <h2>🗓️ Plan your week</h2>
        <button
          type="button"
          className="planner__refresh-button"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing…" : "🔄 Refresh (Notion + Calendar)"}
        </button>
      </div>

      <p className="planner__caption">
        Drag task boxes onto the work blocks you want them in. A short break is implicit
        right after any filled block -- it's never its own event, just time nothing else
        gets scheduled into. Every drag writes to Calendar.app immediately.
      </p>

      {weekRangeError && <p className="planner__error">{weekRangeError}</p>}
      {tasksError && <p className="planner__error">{tasksError}</p>}
      {gridError && <p className="planner__error">{gridError}</p>}
      {actionError && <p className="planner__error">{actionError}</p>}

      {refreshLog && (
        <p className="planner__refresh-summary">
          {refreshLog.removed_count > 0
            ? `Removed ${refreshLog.removed_count} stale/completed calendar block(s).`
            : "Refreshed -- nothing stale found."}
        </p>
      )}

      {tasks && <ActionableTaskList
        tasks={tasks}
        completingPageId={completingPageId}
        onComplete={handleComplete}
      />}

      {weekRange && selectedDay && (
        <DaySelector days={weekRange.days} selectedDay={selectedDay} onSelect={setSelectedDay} />
      )}

      {selectedDay && (
        <ConflictCheckButton
          checked={conflictsChecked}
          busyRowCount={busyRowCount}
          pending={checkingConflicts}
          onCheck={handleCheckConflicts}
        />
      )}

      {!grid && !gridError && selectedDay && <p className="planner__loading">Loading…</p>}

      {grid && tasks && (
        <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
          <TaskPool
            allTasks={tasks}
            poolInstances={poolInstances}
            onPlusOne={handlePlusOne}
            dragDisabled={dragBusy}
          />

          {grid.rows.length === 0 ? (
            <p className="planner__not-working-day">Not a working day.</p>
          ) : (
            <div className={`planner__grid${dragBusy ? " planner__grid--busy" : ""}`}>
              {grid.rows.map((rowState, index) => (
                <GridRow key={index} index={index} rowState={rowState} dragDisabled={dragBusy} />
              ))}
            </div>
          )}

          <DragOverlay>
            {activeDragLabel ? (
              <DraggableTaskBox id="drag-overlay" label={activeDragLabel} />
            ) : null}
          </DragOverlay>
        </DndContext>
      )}
    </section>
  );
}

export default Planner;
