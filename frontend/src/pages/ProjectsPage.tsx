import type { FormEvent } from "react";
import { useState } from "react";

import { EmptyState, ErrorNotice, Loading, Notice } from "../components/ui";
import { api, toApiError } from "../lib/api";
import type { ApiError } from "../lib/api";
import { formatDate } from "../lib/format";
import { useApiData } from "../lib/hooks";
import type { Project, ProjectStats } from "../types";

interface ProjectsData {
  projects: Project[];
  stats: Map<number, ProjectStats | null>;
}

export function ProjectsPage() {
  const { data, error, loading, reload } = useApiData<ProjectsData>(async (signal) => {
    const projects = await api.listProjects(signal);
    const stats = await Promise.all(
      projects.map(async (project) => {
        try {
          const projectStats = await api.getProjectStats(project.id, signal);
          return [project.id, projectStats] as const;
        } catch {
          return [project.id, null] as const;
        }
      }),
    );
    return { projects, stats: new Map(stats) };
  }, []);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const trimmedName = name.trim();
    if (!trimmedName) {
      setFormError(toApiError(new Error("A project name is required.")));
      return;
    }
    setCreating(true);
    try {
      const created = await api.createProject({
        name: trimmedName,
        description: description.trim(),
      });
      setName("");
      setDescription("");
      setNotice({ tone: "ok", text: `Project "${created.name}" created.` });
      reload();
    } catch (failure) {
      setFormError(toApiError(failure));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(projectId: number) {
    setDeletingId(projectId);
    try {
      await api.deleteProject(projectId);
      setConfirmingId(null);
      setNotice({ tone: "ok", text: "Project deleted." });
      reload();
    } catch (failure) {
      setNotice({ tone: "danger", text: toApiError(failure).message });
    } finally {
      setDeletingId(null);
    }
  }

  function focusCreateForm() {
    document.getElementById("new-project-name")?.focus();
  }

  if (!data && loading) {
    return <Loading label="Loading projects…" />;
  }

  if (!data && error) {
    return (
      <section className="card">
        <h1>Projects</h1>
        <ErrorNotice error={error} onRetry={reload} title="Projects could not be loaded" />
      </section>
    );
  }

  const projects = data?.projects ?? [];
  const stats = data?.stats ?? new Map<number, ProjectStats | null>();

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Projects</h1>
          <p className="muted">
            Each project holds one natural-language action, its long videos and the reviewed
            candidate clips.
          </p>
        </div>
        <p className="page-head__count" aria-live="polite">
          {projects.length} {projects.length === 1 ? "project" : "projects"}
        </p>
      </div>

      {notice ? (
        <Notice tone={notice.tone} onDismiss={() => setNotice(null)}>
          <p>{notice.text}</p>
        </Notice>
      ) : null}

      {error ? (
        <ErrorNotice
          error={error}
          onRetry={reload}
          title="Showing the last loaded data — refresh failed"
        />
      ) : null}

      <div className="projects-layout">
        <section aria-labelledby="project-list-heading">
          <h2 id="project-list-heading" className="section-title">
            All projects
          </h2>

          {projects.length === 0 ? (
            <div className="card">
              <EmptyState title="No projects yet">
                <p>
                  Create a project, describe the action you are looking for in natural language,
                  then upload a 10–30 minute single-view RGB video.
                </p>
                <p>
                  <button type="button" className="btn btn--primary" onClick={focusCreateForm}>
                    Create your first project
                  </button>
                </p>
              </EmptyState>
            </div>
          ) : (
            <ul className="project-list">
              {projects.map((project) => {
                const projectStats = stats.get(project.id) ?? null;
                return (
                  <li key={project.id} className="card project-card">
                    <div className="project-card__head">
                      <div>
                        <h3 className="project-card__title">
                          <a href={`#/projects/${project.id}`}>{project.name}</a>
                        </h3>
                        <p className="meta">
                          Created{" "}
                          <time dateTime={project.created_at}>
                            {formatDate(project.created_at)}
                          </time>
                        </p>
                      </div>
                      <a className="btn btn--primary btn--small" href={`#/projects/${project.id}`}>
                        Open project
                      </a>
                    </div>

                    <p className={project.description ? "project-card__desc" : "project-card__desc muted"}>
                      {project.description || "No description."}
                    </p>

                    {projectStats ? (
                      <dl className="mini-stats">
                        <div>
                          <dt>Videos</dt>
                          <dd>
                            {projectStats.videos_ready}/{projectStats.videos_total}
                          </dd>
                        </div>
                        <div>
                          <dt>Candidates</dt>
                          <dd>{projectStats.candidates_total}</dd>
                        </div>
                        <div>
                          <dt>Reviewed</dt>
                          <dd>{projectStats.reviewed_total}</dd>
                        </div>
                        <div>
                          <dt>Unreviewed</dt>
                          <dd>{projectStats.unreviewed_total}</dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="meta">Counts unavailable for this project.</p>
                    )}

                    {confirmingId === project.id ? (
                      <div className="confirm" role="group" aria-label="Confirm project deletion">
                        <p>
                          Delete <strong>{project.name}</strong> and all of its videos, jobs,
                          candidates and exports? This cannot be undone.
                        </p>
                        <div className="row">
                          <button
                            type="button"
                            className="btn btn--danger btn--small"
                            disabled={deletingId === project.id}
                            onClick={() => void handleDelete(project.id)}
                          >
                            {deletingId === project.id ? "Deleting…" : "Yes, delete project"}
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--small"
                            onClick={() => setConfirmingId(null)}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="row">
                        <button
                          type="button"
                          className="btn btn--ghost btn--small"
                          onClick={() => setConfirmingId(project.id)}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <aside className="card create-card" aria-labelledby="new-project-heading">
          <h2 id="new-project-heading">New project</h2>
          <form className="form" onSubmit={(event) => void handleCreate(event)}>
            <div className="field">
              <label htmlFor="new-project-name">Name</label>
              <input
                id="new-project-name"
                name="name"
                type="text"
                required
                maxLength={200}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Cafeteria wave detection"
              />
            </div>
            <div className="field">
              <label htmlFor="new-project-description">Description</label>
              <textarea
                id="new-project-description"
                name="description"
                rows={3}
                maxLength={5000}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What is this dataset for?"
              />
              <p className="field__hint">
                Optional. The action definition inside the project is what the model reads.
              </p>
            </div>

            {formError ? <ErrorNotice error={formError} /> : null}

            <button type="submit" className="btn btn--primary" disabled={creating || !name.trim()}>
              {creating ? "Creating…" : "Create project"}
            </button>
          </form>
        </aside>
      </div>
    </>
  );
}
