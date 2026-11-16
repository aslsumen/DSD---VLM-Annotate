import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { ActionsPanel } from "../components/ActionsPanel";
import { ExportsPanel } from "../components/ExportsPanel";
import { JobsPanel } from "../components/JobsPanel";
import { VideosPanel } from "../components/VideosPanel";
import {
  AriaLive,
  ErrorNotice,
  Loading,
  Notice,
  StatTile,
} from "../components/ui";
import { api, toApiError, type ApiError } from "../lib/api";
import { formatDate } from "../lib/format";
import { useApiData } from "../lib/hooks";
import type {
  ActionDefinition,
  AdaptersResponse,
  DatasetExport,
  Job,
  Project,
  ProjectStats,
  Video,
} from "../types";

interface WorkspaceData {
  project: Project;
  stats: ProjectStats;
  actions: ActionDefinition[];
  videos: Video[];
  jobs: Job[];
  exports: DatasetExport[];
}

type NoticeTone = "ok" | "danger";

export function ProjectPage({ projectId }: { projectId: number }) {
  const workspace = useApiData<WorkspaceData>(async (signal) => {
    const [project, stats, actions, videos, jobs, exports] = await Promise.all([
      api.getProject(projectId, signal),
      api.getProjectStats(projectId, signal),
      api.listActions(projectId, signal),
      api.listVideos(projectId, signal),
      api.listJobs({ projectId }, signal),
      api.listExports(projectId, signal),
    ]);
    return { project, stats, actions, videos, jobs, exports };
  }, [projectId]);

  const adapters = useApiData<AdaptersResponse>(
    (signal) => api.listAdapters(signal),
    [],
  );

  const [notice, setNotice] = useState<{ tone: NoticeTone; text: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<ApiError | null>(null);

  const jobs = workspace.data?.jobs ?? [];
  const jobsActive = jobs.some((job) => job.status === "queued" || job.status === "running");
  const exportsActive =
    workspace.data?.exports.some(
      (datasetExport) =>
        datasetExport.status === "queued" || datasetExport.status === "running",
    ) ?? false;

  useEffect(() => {
    if (!jobsActive && !exportsActive) {
      return;
    }
    const timer = window.setInterval(() => workspace.reload(), 2000);
    return () => window.clearInterval(timer);
  }, [jobsActive, exportsActive, workspace.reload]);

  function notify(text: string, tone: NoticeTone) {
    setNotice({ tone, text });
  }

  function openEditor() {
    if (!workspace.data) {
      return;
    }
    setEditName(workspace.data.project.name);
    setEditDescription(workspace.data.project.description);
    setEditError(null);
    setEditing(true);
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = editName.trim();
    if (!trimmedName) {
      setEditError(toApiError(new Error("The project name must not be blank.")));
      return;
    }
    setSavingEdit(true);
    setEditError(null);
    try {
      const updated = await api.updateProject(projectId, {
        name: trimmedName,
        description: editDescription,
      });
      setEditing(false);
      notify(`Project renamed to "${updated.name}".`, "ok");
      workspace.reload();
    } catch (failure) {
      setEditError(toApiError(failure));
    } finally {
      setSavingEdit(false);
    }
  }

  const queuedCount = jobs.filter((job) => job.status === "queued").length;
  const runningCount = jobs.filter((job) => job.status === "running").length;
  const failedCount = jobs.filter((job) => job.status === "failed").length;
  const jobSummary =
    jobs.length === 0
      ? "No processing jobs."
      : `Jobs: ${queuedCount} queued, ${runningCount} running, ${failedCount} failed.`;

  if (!workspace.data && workspace.loading) {
    return <Loading label="Loading project…" />;
  }

  if (!workspace.data) {
    return (
      <section className="card">
        <p className="breadcrumb">
          <a href="#/">← Back to projects</a>
        </p>
        <h1>Project {projectId}</h1>
        {workspace.error ? (
          <ErrorNotice
            error={workspace.error}
            onRetry={workspace.reload}
            title="This project could not be loaded"
          />
        ) : (
          <Loading label="Reloading project…" />
        )}
      </section>
    );
  }

  const { project, stats, actions, videos, exports } = workspace.data;

  return (
    <>
      <AriaLive message={jobSummary} />

      <section className="page-head project-head">
        <div>
          <p className="breadcrumb">
            <a href="#/">← All projects</a>
          </p>
          <h1>{project.name}</h1>
          <p className="muted">{project.description || "No description."}</p>
          <p className="meta">
            Created <time dateTime={project.created_at}>{formatDate(project.created_at)}</time> ·
            Updated <time dateTime={project.updated_at}>{formatDate(project.updated_at)}</time>
          </p>
        </div>
        <button
          type="button"
          className="btn btn--ghost btn--small"
          onClick={() => (editing ? setEditing(false) : openEditor())}
        >
          {editing ? "Cancel edit" : "Edit project"}
        </button>
      </section>

      {editing ? (
        <form className="card form edit-form" onSubmit={(event) => void handleEdit(event)}>
          <h2>Edit project</h2>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="edit-project-name">Name</label>
              <input
                id="edit-project-name"
                name="name"
                type="text"
                required
                maxLength={200}
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="edit-project-description">Description</label>
              <textarea
                id="edit-project-description"
                name="description"
                rows={3}
                maxLength={5000}
                value={editDescription}
                onChange={(event) => setEditDescription(event.target.value)}
              />
            </div>
          </div>
          {editError ? <ErrorNotice error={editError} /> : null}
          <div className="row">
            <button type="submit" className="btn btn--primary btn--small" disabled={savingEdit}>
              {savingEdit ? "Saving…" : "Save changes"}
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--small"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      {notice ? (
        <Notice tone={notice.tone} onDismiss={() => setNotice(null)}>
          <p>{notice.text}</p>
        </Notice>
      ) : null}

      {workspace.error ? (
        <ErrorNotice
          error={workspace.error}
          onRetry={workspace.reload}
          title="Showing the last loaded data — refresh failed"
        />
      ) : null}

      <section className="card stats-section" aria-labelledby="stats-heading">
        <div className="panel__head">
          <h2 id="stats-heading">Project at a glance</h2>
          <p className="muted">
            {stats.jobs_running} active {stats.jobs_running === 1 ? "job" : "jobs"} ·{" "}
            {stats.jobs_failed} failed · {stats.exports_ready} ready{" "}
            {stats.exports_ready === 1 ? "export" : "exports"}
          </p>
        </div>
        <div className="tiles">
          <StatTile
            label="Videos"
            value={`${stats.videos_ready} / ${stats.videos_total}`}
            hint="ready / total"
          />
          <StatTile label="Candidates" value={stats.candidates_total} />
          <StatTile label="Reviewed" value={stats.reviewed_total} />
          <StatTile label="Unreviewed" value={stats.unreviewed_total} />
          <StatTile label="True positives" value={stats.true_positive_total} />
          <StatTile label="False positives" value={stats.false_positive_total} />
        </div>
      </section>

      <div className="workspace">
        <ActionsPanel
          projectId={projectId}
          actions={actions}
          onChanged={workspace.reload}
          onNotify={notify}
        />

        <VideosPanel
          projectId={projectId}
          videos={videos}
          onChanged={workspace.reload}
          onNotify={notify}
        />

        <JobsPanel
          projectId={projectId}
          jobs={jobs}
          videos={videos}
          actions={actions}
          adapters={adapters.data}
          adaptersLoading={adapters.loading}
          adaptersError={adapters.error}
          onChanged={workspace.reload}
          onNotify={notify}
        />

        <ExportsPanel
          projectId={projectId}
          exports={exports}
          onChanged={workspace.reload}
          onNotify={notify}
        />
      </div>
    </>
  );
}
