import { useState } from "react";
import { apiPost, ApiError } from "../../api/client";
import type { TagCreateRequest, TagOut } from "../../api/types";
import "./TagEditor.css";

// Free-form multi-value tags with a two-level hierarchy (fourth same-day
// follow-up): a "Project" (top-level tag, e.g. "PhD core") and an optional
// sub-tag nested under it (e.g. "Paper 2"). Picking a Project narrows the
// sub-tag suggestions to that project's own children; leaving the sub-tag
// blank adds the Project itself as a tag. Typing a sub-tag name that
// doesn't exist yet creates it (via POST /api/tags, with the chosen
// Project as its parent) at add-time, not deferred to task save -- that's
// the only way its parent gets recorded correctly. Leaving "Project"
// unset falls back to the old flat behavior (creates/adds a top-level tag
// directly by name) for anything that doesn't fit one of the known
// projects.

interface TagEditorProps {
  tags: string[];
  tagTree: TagOut[];
  onChange: (tags: string[]) => void;
  onTagCreated?: () => void;
  disabled?: boolean;
}

export function TagEditor({ tags, tagTree, onChange, onTagCreated, disabled }: TagEditorProps) {
  const [project, setProject] = useState("");
  const [subTag, setSubTag] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const byName = new Map(tagTree.map((t) => [t.name.toLowerCase(), t]));
  const topLevel = tagTree.filter((t) => t.parent === null).map((t) => t.name).sort();
  const subTagSuggestions = project
    ? tagTree.filter((t) => t.parent === project).map((t) => t.name).sort()
    : [];

  function removeTag(name: string) {
    onChange(tags.filter((t) => t !== name));
  }

  function addName(name: string) {
    if (tags.some((t) => t.toLowerCase() === name.toLowerCase())) return;
    onChange([...tags, name]);
  }

  async function handleAdd() {
    setError(null);
    const wantedName = (subTag.trim() || project.trim()).trim();
    if (!wantedName) return;

    const existing = byName.get(wantedName.toLowerCase());
    if (existing) {
      addName(existing.name);
      setSubTag("");
      return;
    }

    // Brand-new tag -- create it (with a parent if one's selected and this
    // wasn't just the project name itself) before attaching it locally, so
    // its place in the hierarchy is recorded from the start.
    setPending(true);
    try {
      const body: TagCreateRequest = {
        name: wantedName,
        parent: subTag.trim() && project.trim() ? project.trim() : null,
      };
      await apiPost<TagOut>("/tags", body);
      addName(wantedName);
      setSubTag("");
      onTagCreated?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't create that tag.");
    } finally {
      setPending(false);
    }
  }

  const disabledAll = disabled || pending;

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

      {error && <p className="tag-editor__error">{error}</p>}

      {!disabled && (
        <div className="tag-editor__picker">
          <select
            value={project}
            onChange={(e) => {
              setProject(e.target.value);
              setSubTag("");
            }}
            disabled={disabledAll}
          >
            <option value="">Project (optional)…</option>
            {topLevel.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <input
            type="text"
            list="tag-editor-subtag-suggestions"
            placeholder={project ? `Sub-tag under ${project}…` : "Tag name…"}
            value={subTag}
            onChange={(e) => setSubTag(e.target.value)}
            disabled={disabledAll}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAdd();
              }
            }}
          />
          <datalist id="tag-editor-subtag-suggestions">
            {subTagSuggestions.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
          <button
            type="button"
            onClick={handleAdd}
            disabled={disabledAll || (!subTag.trim() && !project.trim())}
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

export default TagEditor;
