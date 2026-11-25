/**
 * Search status (DET-3, NFR-9; Design Description v1.2, 4.4 and 5.3):
 * queued → running → done, or failed / partial, with one row per video job.
 */
import { useState } from "react";

import { Dialog, ErrorNotice, Frame, Icon, Loading, Notice, PageHeader, ProgressBar, SearchChip } from "../components/ui";
import { api, toApiError, type ApiError } from "../lib/api";
import { formatDateTime, percent } from "../lib/format";
import { useApiData, useStatusPolling } from "../lib/hooks";
import { deleteSearch as deleteSearchSafely } from "../lib/operations";
import { navigate } from "../lib/router";
import { countReview, isActive, summarizeSearch } from "../lib/search";
import { useSession } from "../lib/session";
import type { Job } from "../types";

async function load(projectId: number, actionId: number, signal: AbortSignal) {
  const [project, actions, videos, jobs, candidates] = await Promise.all([
    api.getProject(projectId, signal),
    api.listActions(projectId, signal),
    api.listVideos(projectId, signal),
    api.listJobs({ projectId, actionId, limit: 200 }, signal),
    api.projectCandidates(projectId, { actionId }, signal),
  ]);
  const action = actions.find((item) => item.id === actionId) ?? null;
  return { project, action, videos, summary: summarizeSearch(jobs), candidates };
}

const JOB_LABEL: Record<Job["status"], string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
  canceled: "Canceled",
};

export function SearchPage({ datasetId, searchId }: { datasetId: number; searchId: number }) {
  const session = useSession();
  const data = useApiData((signal) => load(datasetId, searchId, signal), [datasetId, searchId]);
  const [busyJob, setBusyJob] = useState<number | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const active = data.data ? isActive(data.data.summary.status) : false;
  const reload = data.reload;
  useStatusPolling(data, active, 2500);

  async function jobAction(job: Job, kind: "retry" | "cancel") {
    setBusyJob(job.id);
    setActionError(null);
    try {
      if (kind === "retry") await api.retryJob(job.id);
      else await api.cancelJob(job.id);
    } catch (failure) {
      setActionError(toApiError(failure));
    } finally {
      setBusyJob(null);
      reload();
    }
  }

  async function restartFailed(jobs: Job[]) {
    setActionError(null);
    try {
      for (const job of jobs.filter((item) => item.status === "failed")) {
        await api.retryJob(job.id);
      }
    } catch (failure) {
      setActionError(toApiError(failure));
    }
    reload();
  }

  async function deleteSearch() {
    try {
      await deleteSearchSafely(datasetId, searchId);
      navigate(`/datasets/${datasetId}`);
    } catch (failure) {
      setActionError(toApiError(failure));
      setConfirmDelete(false);
    }
  }

  if (data.loading && !data.data) {
    return (
      <div className="page">
        <Loading label="Loading search…" />
      </div>
    );
  }
  if (!data.data || !data.data.action) {
    return (
      <div className="page">
        <PageHeader title="Search" back={{ href: `#/datasets/${datasetId}`, label: "Dataset" }} />
        {data.error ? (
          <ErrorNotice error={data.error} onRetry={reload} />
        ) : (
          <Notice tone="warning">This search does not exist anymore.</Notice>
        )}
      </div>
    );
  }

  const { project, action, videos, summary, candidates } = data.data;
  const videoName = new Map(videos.map((video) => [video.id, video.original_filename]));
  const counts = countReview(candidates);
  const status = summary.status;
  const finished = status === "done" || status === "partial";
  const failedJobs = summary.jobs.filter((job) => job.status === "failed");

  const steps = [
    { label: "Queued", sub: `${summary.videosTotal} ${summary.videosTotal === 1 ? "video" : "videos"}`, state: "done" },
    {
      label: "Running",
      sub: status === "queued" ? "waiting" : `${summary.videosDone} of ${summary.videosTotal} processed`,
      state: status === "queued" ? "todo" : status === "running" ? "current" : "done",
    },
    {
      label: finished ? "Done" : status === "failed" ? "Failed" : "Done",
      sub: finished || status === "failed" ? `${counts.all} candidates` : "—",
      state: finished ? "done" : status === "failed" ? "failed" : "todo",
    },
  ];

  return (
    <div className="page page--medium">
      <PageHeader
        back={{ href: `#/datasets/${datasetId}`, label: project.name }}
        kicker="Search"
        title={action.name}
        subtitle={<span className="prompt-quote">“{action.description}”</span>}
        actions={
          session.canManage ? (
            <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(true)}>
              <Icon name="trash" size={14} />
              Delete search
            </button>
          ) : null
        }
      />

      <div className="steps">
        {steps.map((step, index) => (
          <div key={step.label + index} className={`step step--${step.state}`}>
            <span className="step__mark">{step.state === "done" ? "✓" : step.state === "failed" ? "!" : index + 1}</span>
            <span className="step__text">
              <span className="strong">{step.label}</span>
              <span className="muted small">{step.sub}</span>
            </span>
          </div>
        ))}
      </div>

      {data.error ? <ErrorNotice error={data.error} onRetry={reload} title="Refresh failed" /> : null}
      {actionError ? <ErrorNotice error={actionError} title="The action failed" /> : null}

      <Frame className="status-frame">
        <div className="status-frame__chip">
          <SearchChip status={status} progress={summary.progress} />
          {summary.adapters.length ? <span className="muted small">Model: {summary.adapters.join(", ")}</span> : null}
        </div>
        {status === "queued" ? (
          <>
            <h3>Waiting in the queue</h3>
            <p className="muted">
              The search will start automatically when a worker is free. You can leave this page.
            </p>
          </>
        ) : null}
        {status === "running" ? (
          <>
            <div className="row-between">
              <h3>Searching the videos</h3>
              <span className="big-figure">{percent(summary.progress)}</span>
            </div>
            <ProgressBar value={summary.progress} label="Search progress" thick />
            <div className="muted small tabular">
              {summary.videosDone} of {summary.videosTotal} videos processed
            </div>
            <p className="muted small">
              You can leave this page. Processing continues in the background and the search will show as Done in
              the dataset.
            </p>
          </>
        ) : null}
        {finished && counts.all > 0 ? (
          <>
            <h3>
              {counts.all} {counts.all === 1 ? "candidate" : "candidates"} in {summary.videosDone}{" "}
              {summary.videosDone === 1 ? "video" : "videos"}
            </h3>
            <p className="muted">
              {counts.unreviewed} unreviewed · {counts.accepted} accepted · {counts.rejected} rejected
            </p>
            {status === "partial" ? (
              <Notice tone="warning" title="Partial results">
                {failedJobs.length} {failedJobs.length === 1 ? "video" : "videos"} could not be processed. Results
                for the other videos are ready.
              </Notice>
            ) : null}
            <div className="row">
              <a className="btn btn-primary btn-lg" href={`#/datasets/${datasetId}/searches/${searchId}/review`}>
                Review candidates
              </a>
              {session.canManage && status === "partial" ? (
                <button type="button" className="btn btn-secondary" onClick={() => void restartFailed(summary.jobs)}>
                  <Icon name="restart" size={14} />
                  Restart failed videos
                </button>
              ) : null}
            </div>
          </>
        ) : null}
        {finished && counts.all === 0 ? (
          <>
            <h3>No candidates found</h3>
            <p className="muted">
              The model didn’t find this action in any of the videos. Try describing it differently: what is
              visible, who does it, where in the frame.
            </p>
            {session.canManage ? (
              <a className="btn btn-secondary align-start" href={`#/datasets/${datasetId}/searches/new`}>
                New search
              </a>
            ) : null}
          </>
        ) : null}
        {status === "failed" ? (
          <>
            <Notice tone="danger" title="The search failed">
              {failedJobs[0]?.error_message ?? "Every video job failed."}
            </Notice>
            {session.canManage ? (
              <button type="button" className="btn btn-primary align-start" onClick={() => void restartFailed(summary.jobs)}>
                <Icon name="restart" size={14} />
                Restart search
              </button>
            ) : null}
          </>
        ) : null}
        {status === "empty" ? (
          <p className="muted">This search has no video jobs. Upload videos and start a new search.</p>
        ) : null}
      </Frame>

      {summary.adapters.includes("mock") ? (
        <Notice tone="warning" title="Mock model">
          These candidates come from the mock model: no video pixels were analysed.
        </Notice>
      ) : null}

      <section className="stack">
        <h3>Videos in this search</h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Video</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Model</th>
                <th>Updated</th>
                {session.canManage ? <th className="right">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {summary.jobs.map((job) => (
                <tr key={job.id}>
                  <td className="truncate">{job.video_id ? videoName.get(job.video_id) ?? `Video ${job.video_id}` : "—"}</td>
                  <td>
                    <span className={`chip chip--job-${job.status}`} title={job.error_message ?? undefined}>
                      {JOB_LABEL[job.status]}
                    </span>
                    {job.error_code ? <div className="muted small">{job.error_code}</div> : null}
                  </td>
                  <td className="tabular">
                    {percent(job.status === "succeeded" ? 1 : job.progress)}
                    {job.attempts > 1 ? <span className="muted small"> · attempt {job.attempts}</span> : null}
                  </td>
                  <td className="small">{job.adapter_name ?? "—"}</td>
                  <td className="muted small">{formatDateTime(job.finished_at ?? job.started_at ?? job.created_at)}</td>
                  {session.canManage ? (
                    <td className="right">
                      {job.status === "failed" ? (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={busyJob === job.id}
                          onClick={() => void jobAction(job, "retry")}
                        >
                          Retry
                        </button>
                      ) : null}
                      {job.status === "queued" || job.status === "running" ? (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={busyJob === job.id}
                          onClick={() => void jobAction(job, "cancel")}
                        >
                          Cancel
                        </button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {confirmDelete ? (
        <Dialog
          title="Delete this search?"
          onClose={() => setConfirmDelete(false)}
          actions={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
                Cancel
              </button>
              <button type="button" className="btn btn-danger" onClick={() => void deleteSearch()}>
                Delete search
              </button>
            </>
          }
        >
          <p>
            The prompt “{action.description}” is removed from the dataset. Queued and running jobs of this search
            are canceled first.
          </p>
          {counts.accepted + counts.rejected > 0 ? (
            <Notice tone="warning" title="Review decisions will be lost">
              Its {counts.all} candidates are deleted, including {counts.accepted + counts.rejected} already
              reviewed. They will not be exported. This cannot be undone.
            </Notice>
          ) : (
            <p className="muted small">
              Its {counts.all} candidates and their preview clips are deleted too. This cannot be undone.
            </p>
          )}
        </Dialog>
      ) : null}
    </div>
  );
}
