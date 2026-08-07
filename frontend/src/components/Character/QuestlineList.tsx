import type { QuestlineOut } from "../../api/types";
import "./QuestlineList.css";

// Mirrors app.py's Questlines subsection format exactly:
//   📜 **{project}** — {N} sessions ({M} milestone(s) claimed)
// CharacterPanel only renders this component when there's at least one
// active questline (matching app.py's `if active_questlines:` guard), so
// no empty state to handle here.

interface QuestlineListProps {
  questlines: QuestlineOut[];
}

export function QuestlineList({ questlines }: QuestlineListProps) {
  return (
    <div className="questline-list">
      <h3>Questlines</h3>
      <ul className="questline-list__list">
        {questlines.map((q) => (
          <li key={q.project_name}>
            📜 <strong>{q.project_name}</strong> — {q.session_count} sessions (
            {q.milestones_paid} milestone(s) claimed)
          </li>
        ))}
      </ul>
    </div>
  );
}

export default QuestlineList;
