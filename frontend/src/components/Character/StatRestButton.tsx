import "./StatRestButton.css";

// Mirrors app.py's per-stat column: stat name, "lvl {level}", and a
// "Rest ({cost} Runes)" button disabled when `runes < cost` -- exactly
// app.py's `disabled=c.runes < cost`. `pending` additionally disables the
// button while this stat's rest request is in flight, so a slow request
// can't be double-submitted.

interface StatRestButtonProps {
  statName: string;
  level: number;
  cost: number;
  runes: number;
  pending: boolean;
  onRest: () => void;
}

export function StatRestButton({
  statName,
  level,
  cost,
  runes,
  pending,
  onRest,
}: StatRestButtonProps) {
  const disabled = pending || runes < cost;
  return (
    <div className="stat-rest-button">
      <p className="stat-rest-button__name">{statName}</p>
      <p className="stat-rest-button__level">lvl {level}</p>
      <button
        type="button"
        className="stat-rest-button__button"
        disabled={disabled}
        onClick={onRest}
      >
        Rest ({cost} Runes)
      </button>
    </div>
  );
}

export default StatRestButton;
