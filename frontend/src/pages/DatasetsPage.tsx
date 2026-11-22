/**
 * Datasets list (DS-2, USR-3; Design Description v1.2, 5.3).
 *
 * In the current API a dataset is backed by a project: projects hold the videos,
 * prompts (actions), jobs, candidates and exports.
 */
import { useState } from "react";

import { Dialog, EmptyState, ErrorNotice, Frame, Icon, PageHeader, ProgressBar } from "../components/ui";
import { api, toApiError, type ApiError } from "../lib/api";
import { formatDate, percent } from "../lib/format";
import { useApiData } from "../lib/hooks";
import { navigate } from "../lib/router";
import { useSession } from "../lib/session";
import type { Project, ProjectStats } from "../types";

interface DatasetCardData {
  project: Project;
  stats: ProjectStats | null;
  searches: number;
}

async function loadCards(signal: AbortSignal): Promise<DatasetCardData[]> {
  const projects = await api.listProjects(signal);
  return Promise.all(
    projects.map(async (project) => {
      const [stats, actions] = await Promise.all([
        api.getProjectStats(project.id, signal).catch(() => null),
        api.listActions(project.id, signal).catch(() => []),
      ]);
      return { project, stats, searches: actions.length };
    }),
  );
}

function DatasetCard({ data }: { data: DatasetCardData }) {
  const { project, stats, searches } = data;
  const total = stats?.candidates_total ?? 0;
  const reviewed = stats?.reviewed_total ?? 0;
  return (
    <a className="blueprint dataset-card" href={`#/datasets/${project.id}`}>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
      <div className="dataset-card__head">
        <span className="muted small">Created {formatDate(project.created_at)}</span>
        <span className="dataset-card__name">{project.name}</span>
      </div>
      <div className="dataset-card__stats">
        <div>
          <span className="figure">{stats?.videos_total ?? "—"}</span>
          <span className="muted small">Videos</span>
        </div>
        <div>
          <span className="figure">{searches}</span>
          <span className="muted small">Searches</span>
        </div>
      </div>
      <div className="dataset-card__progress">
        <div className="row-between small">
          <span className="muted">Review progress</span>
          <span className="tabular">
            {total ? `${reviewed} / ${total} · ${percent(reviewed / total)}` : "No candidates yet"}
          </span>
        </div>
        <ProgressBar value={total ? reviewed / total : 0} label={`Review progress of ${project.name}`} />
      </div>
    </a>
  );
}

function NewDatasetDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject({ name: name.trim() });
      navigate(`/datasets/${project.id}`);
    } catch (failure) {
      setError(toApiError(failure));
      setBusy(false);
    }
  }

  return (
    <Dialog
      title="New dataset"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!name.trim() || busy}
            onClick={() => void create()}
          >
            {busy ? "Creating…" : "Create dataset"}
          </button>
        </>
      }
    >
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) void create();
        }}
      >
        <div className="field">
          <label htmlFor="dataset-name">Name</label>
          <input
            id="dataset-name"
            className="input"
            value={name}
            maxLength={200}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Warehouse operations"
          />
        </div>
        <div className="muted small">Name it after its use case. You can upload videos after the dataset is created.</div>
        {error ? <ErrorNotice error={error} title="Could not create the dataset" /> : null}
      </form>
    </Dialog>
  );
}

export function DatasetsPage() {
  const session = useSession();
  const cards = useApiData((signal) => loadCards(signal), []);
  const [creating, setCreating] = useState(false);

  const count = cards.data?.length ?? 0;
  const subtitle = cards.data
    ? `${count} ${count === 1 ? "dataset" : "datasets"}${session.canManage ? "" : " assigned to you"}`
    : "Loading datasets…";

  return (
    <div className="page">
      <PageHeader
        kicker="Workspace"
        title="Datasets"
        subtitle={subtitle}
        actions={
          session.canManage ? (
            <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
              <Icon name="plus" />
              New dataset
            </button>
          ) : null
        }
      />

      {cards.error ? <ErrorNotice error={cards.error} onRetry={cards.reload} /> : null}

      {cards.loading && !cards.data ? (
        <div className="card-grid">
          {[0, 1, 2].map((index) => (
            <Frame key={index} className="dataset-card skeleton">
              <div className="skeleton__line w30" />
              <div className="skeleton__line w70 tall" />
              <div className="skeleton__block" />
            </Frame>
          ))}
        </div>
      ) : null}

      {cards.data && cards.data.length > 0 ? (
        <div className="card-grid">
          {cards.data.map((data) => (
            <DatasetCard key={data.project.id} data={data} />
          ))}
        </div>
      ) : null}

      {cards.data && cards.data.length === 0 ? (
        <Frame className="empty-frame">
          <EmptyState title={session.canManage ? "No datasets yet" : "No datasets assigned to you yet"}>
            {session.canManage
              ? "Create a dataset, upload MP4 videos, then run a search."
              : "When an administrator assigns you to a dataset, it will appear here."}
          </EmptyState>
        </Frame>
      ) : null}

      {creating ? <NewDatasetDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}
