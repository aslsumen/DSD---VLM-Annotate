import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { EmptyState, ErrorNotice, ProgressBar, StatusChip } from "../components/ui";
import {
  api,
  newIdempotencyKey,
  toApiError,
  type ApiError,
} from "../lib/api";
import { formatDateTime, percent } from "../lib/format";
import type { ActionDefinition, AdaptersResponse, Job, Video } from "../types";

interface JobsPanelProps {
  projectId: number;
  jobs: Job[];
  videos: Video[];
  actions: ActionDefinition[];
  adapters: AdaptersResponse | null;
  adaptersLoading: boolean;
  adaptersError: ApiError | null;
  onChanged: () => void;
  onNotify: (text: string, tone: "ok" | "danger") => void;
}

function jobKindLabel(kind: Job["kind"]): string {
  return kind === "dataset_export" ? "Dataset export" : "Candidate proposal";
}

export function JobsPanel({
  projectId,
  jobs,
  videos,
  actions,
  adapters,
  adaptersLoading,
  adaptersError,
  onChanged,
  onNotify,
}: JobsPanelProps) {
  const [videoId, setVideoId] = useState("");
  const [actionId, setActionId] = useState("");
  const [adapterName, setAdapterName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [busyJobId, setBusyJobId] = useState<number | null>(null);

  // Keep selections valid as videos/actions are created or deleted.
  useEffect(() => {
    setVideoId((current) => {
      if (current && videos.some((video) => String(video.id) === current)) {
        return current;
      }
      const firstReady = videos.find((video) => video.status === "ready") ?? videos[0];
      return firstReady ? String(firstReady.id) : "";
    });
  }, [videos]);

  useEffect(() => {
    setActionId((current) => {
      if (current && actions.some((action) => String(action.id) === current)) {
        return current;
      }
      return actions[0] ? String(actions[0].id) : "";
    });
  }, [actions]);

  useEffect(() => {
    if (!adapters) {
      return;
    }
    setAdapterName((current) => {
      if (current && adapters.adapters.some((adapter) => adapter.name === current)) {
        return current;
      }
      return adapters.default;
    });
  }, [adapters]);

  const selectedVideo = videos.find((video) => String(video.id) === videoId) ?? null;
  const selectedAction = actions.find((action) => String(action.id) === actionId) ?? null;
  const selectedAdapter =
    adapters?.adapters.find((adapter) => adapter.name === adapterName) ?? null;

  const blockingReason = (() => {
    if (actions.length === 0) {
      return "Add an action definition first — the VLM needs natural-language text to search for.";
    }
    if (videos.length === 0) {
      return "Upload a video first.";
    }
    if (!selectedVideo) {
      return "Choose a video.";
    }
    if (selectedVideo.status !== "ready") {
      return `"${selectedVideo.original_filename}" is ${selectedVideo.status}; only ready videos can be processed.`;
    }
    if (!selectedAction) {
      return "Choose an action definition.";
    }
    if (selectedAdapter && !selectedAdapter.available) {
      return `Adapter "${selectedAdapter.name}" is registered but unavailable in this deployment.`;
    }
    return null;
  })();

  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedVideo || !selectedAction) {
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const job = await api.createJob(
        selectedVideo.id,
        {
          action_id: selectedAction.id,
          ...(selectedAdapter ? { adapter: selectedAdapter.name } : {}),
        },
        newIdempotencyKey(),
      );
      onNotify(
        `Job #${job.id} queued for "${selectedVideo.original_filename}" with adapter ${
          job.adapter_name ?? "the server default"
        }.`,
        "ok",
      );
      onChanged();
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRetry(job: Job) {
    setBusyJobId(job.id);
    try {
      await api.retryJob(job.id);
      onNotify(`Job #${job.id} queued again.`, "ok");
      onChanged();
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setBusyJobId(null);
    }
  }

  async function handleCancel(job: Job) {
    setBusyJobId(job.id);
    try {
      await api.cancelJob(job.id);
      onNotify(`Job #${job.id} cancelled.`, "ok");
      onChanged();
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setBusyJobId(null);
    }
  }

  return (
    <section className="card panel" aria-labelledby="jobs-heading">
      <div className="panel__head">
        <h2 id="jobs-heading">Processing jobs</h2>
        <p className="muted">
          VLM inference runs asynchronously. This list refreshes every 2 seconds while a job is
          queued or running.
        </p>
      </div>

      <form className="form start-form" onSubmit={(event) => void handleStart(event)}>
        <h3 className="form__title">Start processing</h3>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="job-video">Video</label>
            <select
              id="job-video"
              name="video"
              value={videoId}
              onChange={(event) => setVideoId(event.target.value)}
              disabled={videos.length === 0}
            >
              {videos.length === 0 ? <option value="">No videos</option> : null}
              {videos.map((video) => (
                <option key={video.id} value={video.id}>
                  {video.original_filename}
                  {video.status === "ready" ? "" : ` (${video.status})`}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="job-action">Action</label>
            <select
              id="job-action"
              name="action"
              value={actionId}
              onChange={(event) => setActionId(event.target.value)}
              disabled={actions.length === 0}
            >
              {actions.length === 0 ? <option value="">No actions</option> : null}
              {actions.map((action) => (
                <option key={action.id} value={action.id}>
                  {action.name}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="job-adapter">Adapter</label>
            <select
              id="job-adapter"
              name="adapter"
              value={adapterName}
              onChange={(event) => setAdapterName(event.target.value)}
              disabled={!adapters || adapters.adapters.length === 0}
            >
              {!adapters ? (
                <option value="">
                  {adaptersLoading ? "Loading adapters…" : "Server default"}
                </option>
              ) : null}
              {adapters
                ? adapters.adapters.map((adapter) => (
                    <option key={adapter.name} value={adapter.name} disabled={!adapter.available}>
                      {adapter.name} ({adapter.version})
                      {adapter.available ? "" : " — unavailable"}
                      {adapter.requires_gpu ? " · GPU" : ""}
                    </option>
                  ))
                : null}
            </select>
            {selectedAdapter ? (
              <p className="field__hint">
                {selectedAdapter.requires_gpu ? "Requires a GPU. " : ""}
                {selectedAdapter.available ? "Available." : "Not available in this deployment."}
              </p>
            ) : null}
          </div>
        </div>

        {adaptersError ? (
          <p className="field__hint field__hint--warn">
            Adapter catalogue unavailable ({adaptersError.code}). The server default will be used.
          </p>
        ) : null}

        {blockingReason ? (
          <p className="field__hint field__hint--warn" id="start-blocked-reason">
            {blockingReason}
          </p>
        ) : (
          <p className="field__hint" id="start-blocked-reason">
            {selectedVideo
              ? `Will analyse ${selectedVideo.original_filename}. Only human review can mark a candidate as a true or false positive.`
              : "Choose a video and an action."}
          </p>
        )}

        {error ? <ErrorNotice error={error} title="The job could not be queued" /> : null}

        <button
          type="submit"
          className="btn btn--primary"
          disabled={submitting || blockingReason !== null}
          aria-describedby="start-blocked-reason"
        >
          {submitting ? "Queueing…" : "Start processing"}
        </button>
      </form>

      <h3 className="form__title">Job history</h3>
      {jobs.length === 0 ? (
        <EmptyState title="No processing jobs yet">
          <p>Queue a job above. Its progress and any errors will appear here.</p>
        </EmptyState>
      ) : (
        <ul className="job-list">
          {jobs.map((job) => {
            const video = job.video_id
              ? videos.find((candidate) => candidate.id === job.video_id) ?? null
              : null;
            const action = job.action_id
              ? actions.find((candidate) => candidate.id === job.action_id) ?? null
              : null;
            return (
              <li key={job.id} className="job">
                <div className="job__head">
                  <div className="job__title">
                    <h4>Job #{job.id}</h4>
                    <span className="meta">{jobKindLabel(job.kind)}</span>
                  </div>
                  <StatusChip status={job.status} />
                </div>

                <div className="job__progress">
                  <ProgressBar value={job.progress} label={`Job ${job.id} progress`} />
                  <span className="meta">{percent(job.progress)}</span>
                </div>

                <dl className="job-meta">
                  <div>
                    <dt>Video</dt>
                    <dd>
                      {video
                        ? video.original_filename
                        : job.video_id
                          ? `#${job.video_id} (deleted)`
                          : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Action</dt>
                    <dd>
                      {action
                        ? action.name
                        : job.action_id
                          ? `#${job.action_id} (deleted)`
                          : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Adapter</dt>
                    <dd>
                      {job.adapter_name ?? "—"}
                      {job.adapter_version ? ` v${job.adapter_version}` : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>Attempts</dt>
                    <dd>
                      {job.attempts} / {job.max_attempts}
                    </dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>{formatDateTime(job.created_at)}</dd>
                  </div>
                  {job.finished_at ? (
                    <div>
                      <dt>Finished</dt>
                      <dd>{formatDateTime(job.finished_at)}</dd>
                    </div>
                  ) : null}
                </dl>

                {job.error_message ? (
                  <p className="error-text">
                    {job.error_code ? <code className="error-code">{job.error_code}</code> : null}{" "}
                    {job.error_message}
                  </p>
                ) : null}

                <div className="row">
                  {job.kind === "candidate_proposal" && job.status === "succeeded" ? (
                    <a
                      className="btn btn--primary btn--small"
                      href={`#/projects/${projectId}/review?job=${job.id}`}
                    >
                      Review candidates
                    </a>
                  ) : null}
                  {job.status === "failed" ? (
                    <button
                      type="button"
                      className="btn btn--ghost btn--small"
                      disabled={busyJobId === job.id}
                      onClick={() => void handleRetry(job)}
                    >
                      {busyJobId === job.id ? "Retrying…" : "Retry"}
                    </button>
                  ) : null}
                  {job.status === "queued" ? (
                    <button
                      type="button"
                      className="btn btn--ghost btn--small"
                      disabled={busyJobId === job.id}
                      onClick={() => void handleCancel(job)}
                    >
                      {busyJobId === job.id ? "Cancelling…" : "Cancel"}
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
