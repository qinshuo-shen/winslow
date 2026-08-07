import "./ConflictCheckButton.css";

// The opt-in "🔍 Check conflicts" button, per day -- must stay a manual
// click, never auto-triggered, since it's backed by
// calendar_bridge.list_busy_events(), a documented ~30s-per-day AppleScript
// call across the user's external ("busy") calendars.

interface ConflictCheckButtonProps {
  checked: boolean;
  busyRowCount: number | null;
  pending: boolean;
  onCheck: () => void;
}

export function ConflictCheckButton({
  checked,
  busyRowCount,
  pending,
  onCheck,
}: ConflictCheckButtonProps) {
  return (
    <div className="conflict-check">
      <button
        type="button"
        className="conflict-check__button"
        onClick={onCheck}
        disabled={pending}
      >
        {pending ? "Checking (can take up to ~30s)…" : "🔍 Check conflicts"}
      </button>
      <span className="conflict-check__status">
        {checked
          ? `Conflict-checked (${busyRowCount ?? 0} busy row(s)).`
          : "Conflicts not checked yet for this day."}
      </span>
    </div>
  );
}

export default ConflictCheckButton;
