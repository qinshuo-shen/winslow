import { useEffect, useState } from "react";
import { apiDelete, apiGet, ApiError } from "../../api/client";
import type { ProjectOut, TagOut } from "../../api/types";
import { ProjectCard } from "./ProjectCard";
import { NewProjectModal } from "./NewProjectModal";
import { ProjectRoadmapModal } from "./ProjectRoadmapModal";
import "../Board/Board.css";
import "./Projects.css";

// Page 2, "Project tracking" -- parallels Board.tsx's own structure
// (fetch-on-mount, a card grid, conditional-render-from-local-state
// modals) so a project reads visually like a task, per the user's ask,
// while staying a genuinely separate entity (see procrastination_tool/
// projects.py's docstring for why it isn't built on the existing tag
// Project/sub-project hierarchy).

export function ProjectBoard() {
  const [projects, setProjects] = useState<ProjectOut[] | null>(null);
  const [tagTree, setTagTree] = useState<TagOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);
  const [roadmapProject, setRoadmapProject] = useState<ProjectOut | null>(null);

  async function refresh() {
    try {
      const data = await apiGet<ProjectOut[]>("/projects");
      setProjects(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your projects.");
    }
  }

  async function refreshTags() {
    try {
      setTagTree(await apiGet<TagOut[]>("/tags"));
    } catch {
      // Non-critical -- the tag editor just falls back to empty.
    }
  }

  useEffect(() => {
    refresh();
    refreshTags();
  }, []);

  async function handleDelete(id: number) {
    setPending(true);
    setError(null);
    try {
      await apiDelete(`/projects/${id}`);
      setProjects((prev) => prev?.filter((p) => p.id !== id) ?? prev);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove that project.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="board">
      <div className="board__header">
        <h2>Projects</h2>
        <button type="button" className="board__new-task" onClick={() => setShowNewProject(true)}>
          + New project
        </button>
      </div>

      {error && <p className="board__error">{error}</p>}

      {projects === null && !error && <p className="board__loading">Loading…</p>}

      {projects !== null && projects.length === 0 && (
        <p className="board__quadrant-empty">
          Nothing here yet -- register a project once something will naturally take more than one task.
        </p>
      )}

      {projects !== null && projects.length > 0 && (
        <ul className="project-board__grid">
          {projects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              pending={pending}
              onOpen={() => setRoadmapProject(p)}
              onDelete={() => handleDelete(p.id)}
            />
          ))}
        </ul>
      )}

      {showNewProject && (
        <NewProjectModal
          tagTree={tagTree}
          onClose={() => setShowNewProject(false)}
          onCreated={(created) => {
            setProjects((prev) => (prev ? [...prev, created] : [created]));
            refreshTags();
          }}
          onTagCreated={refreshTags}
        />
      )}

      {roadmapProject && (
        <ProjectRoadmapModal
          project={roadmapProject}
          tagTree={tagTree}
          onClose={() => setRoadmapProject(null)}
          onSaved={(updated) => {
            setProjects((prev) => prev?.map((p) => (p.id === updated.id ? updated : p)) ?? prev);
            setRoadmapProject(updated);
            refreshTags();
          }}
          onTagCreated={refreshTags}
        />
      )}
    </section>
  );
}

export default ProjectBoard;
