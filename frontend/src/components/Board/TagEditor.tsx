import { useState } from "react";
import "./TagEditor.css";

// Free-form multi-value tags (mirrors Notion's 'Block'/'Specific Project'
// select properties, folded together on import -- see
// migrate_notion_tasks.py). Typing a name not already in `availableTags`
// and pressing Enter/clicking Add creates it on save (tasks.py's
// set_task_tags does the actual get-or-create) -- there's no separate
// "manage tags" step, same as how Notion lets you type a new option
// directly into a multi-select.

interface TagEditorProps {
  tags: string[];
  availableTags: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
}

export function TagEditor({ tags, availableTags, onChange, disabled }: TagEditorProps) {
  const [draft, setDraft] = useState("");

  function addTag(raw: string) {
    const name = raw.trim();
    if (!name || tags.some((t) => t.toLowerCase() === name.toLowerCase())) return;
    onChange([...tags, name]);
    setDraft("");
  }

  function removeTag(name: string) {
    onChange(tags.filter((t) => t !== name));
  }

  const suggestions = availableTags.filter((t) => !tags.some((tag) => tag.toLowerCase() === t.toLowerCase()));

  return (
    <div className="tag-editor">
      <div className="tag-editor__chips">
        {tags.map((t) => (
          <span key={t} className="tag-editor__chip">
            {t}
            {!disabled && (
              <button
                type="button"
                className="tag-editor__chip-remove"
                onClick={() => removeTag(t)}
                aria-label={`Remove tag ${t}`}
              >
                ×
              </button>
            )}
          </span>
        ))}
      </div>
      {!disabled && (
        <form
          className="tag-editor__form"
          onSubmit={(e) => {
            e.preventDefault();
            addTag(draft);
          }}
        >
          <input
            type="text"
            list="tag-editor-suggestions"
            placeholder="Add a tag…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <datalist id="tag-editor-suggestions">
            {suggestions.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
          <button type="submit" disabled={!draft.trim()}>
            Add
          </button>
        </form>
      )}
    </div>
  );
}

export default TagEditor;
