// Maps each of the 4 Impact/Effort quadrants to a stable CSS class suffix,
// so the Board can give each one a distinct, consistent tint (see
// Board.css) -- purely a visual grouping aid, not meaningful data. Keyed by
// the literal priority string (not PRIORITY_QUADRANTS array index) so this
// stays correct regardless of what order that array renders columns in.
const QUADRANT_CLASS: Record<string, string> = {
  "Major Projects (High Impact-High Effort)": "major",
  "Thankless Tasks (Low Impact-High Effort)": "thankless",
  "Quick Wins (High Impact-Low Effort)": "quick",
  "Fill-ins (Low Impact-Low Effort)": "fillins",
};

export function quadrantClass(priority: string): string {
  return QUADRANT_CLASS[priority] ?? "quick";
}
