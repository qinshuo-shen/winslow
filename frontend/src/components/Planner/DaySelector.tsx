import "./DaySelector.css";

// A day-tabs row, matching app.py's st.radio(horizontal=True) feel -- a
// simple button/tab row, not a <select>. Only one day is ever mounted at a
// time (via the parent's selectedDay state), same reasoning app.py's
// comment gives for using st.radio over st.tabs: keeping only one day's
// grid mounted avoids a repeated-mutation update-depth blowup from mounting
// several drag-and-drop widgets simultaneously.

function formatDayLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const weekday = d.toLocaleDateString(undefined, { weekday: "short" });
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${weekday} ${mm}/${dd}`;
}

interface DaySelectorProps {
  days: string[];
  selectedDay: string;
  onSelect: (day: string) => void;
}

export function DaySelector({ days, selectedDay, onSelect }: DaySelectorProps) {
  return (
    <div className="day-selector" role="tablist" aria-label="Select day to plan">
      {days.map((day) => (
        <button
          key={day}
          type="button"
          role="tab"
          aria-selected={day === selectedDay}
          className={`day-selector__tab${
            day === selectedDay ? " day-selector__tab--active" : ""
          }`}
          onClick={() => onSelect(day)}
        >
          {formatDayLabel(day)}
        </button>
      ))}
    </div>
  );
}

export default DaySelector;
