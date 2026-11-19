/**
 * Dataset page (DS-1, DS-2, DS-4, DS-7, PR-1, DET-3, REV-4, NFR-9;
 * Design Description v1.2, 5.3): videos with upload, and one row per search.
 */
import type { DragEvent } from "react";
import { useEffect, useRef, useState } from "react";

import {
  Dialog,
  EmptyState,
  ErrorNotice,
  Icon,
  Loading,
  Notice,
  PageHeader,
  ProgressBar,
  SearchChip,
  Toast,
} from "../components/ui";
import { api, newIdempotencyKey, toApiError, type ApiError } from "../lib/api";
import { formatBytes, formatClock, formatDate, formatResolution, percent } from "../lib/format";
import { useApiData } from "../lib/hooks";
import { navigate } from "../lib/router";
import { countReview, isActive, summarizeSearch, type SearchSummary } from "../lib/search";
import { useSession } from "../lib/session";
import type { ActionDefinition, Candidate, Project, Video } from "../types";

export interface DatasetData {
  project: Project;
  videos: Video[];
  actions: ActionDefinition[];
  summaries: Map<number, SearchSummary>;
  candidatesByAction: Map<number, Candidate[]>;
}

export async function loadDataset(projectId: number, signal: AbortSignal): Promise<DatasetData> {
  const [project, videos, actions, jobs, candidates] = await Promise.all([
    api.getProject(projectId, signal),
    api.listVideos(projectId, signal),
    api.listActions(projectId, signal),
    api.listJobs({ projectId, limit: 200 }, signal),
    api.projectCandidates(projectId, {}, signal),
  ]);
  const summaries = new Map<number, SearchSummary>();
  for (const action of actions) {
    summaries.set(action.id, summarizeSearch(jobs.filter((job) => job.action_id === action.id)));
  }
  const candidatesByAction = new Map<number, Candidate[]>();
  for (const candidate of candidates) {
    if (candidate.action_id === null) continue;
    const list = candidatesByAction.get(candidate.action_id) ?? [];
    list.push(candidate);
    candidatesByAction.set(candidate.action_id, list);
  }
  return { project, videos, actions, summaries, candidatesByAction };
}

const MAX_SECONDS_MVP = 300; // DS-4

interface UploadState {
  name: string;
  index: number;
  total: number;
  fraction: number;
}

function SearchRow({
  datasetId,
  action,
  summary,
  candidates,
  canManage,
  onRestart,
}: {
  datasetId: number;
  action: ActionDefinition;
  summary: SearchSummary;
  candidates: Candidate[];
  canManage: boolean;
  onRestart: () => void;
}) {
  const counts = countReview(candidates);
  const reviewed = counts.accepted + counts.rejected;
  const finished = summary.status === "done" || summary.status === "partial";
  const target = finished && counts.all > 0 ? "review" : "";
  const url = `/datasets/${datasetId}/searches/${action.id}${target ? "/review" : ""}`;

  return (
    <div className="search-row">
      <a className="search-row__main" href={`#${url}`}>
        <span className="search-row__title">{action.name}</span>
        <span className="search-row__prompt">“{action.description}”</span>
      </a>
      <div className="search-row__status">
        <SearchChip status={summary.status} progress={summary.progress} />
      </div>
      <div className="search-row__meta tabular">
        <span>
          {summary.status === "running" || summary.status === "queued"
            ? `${summary.videosDone} of ${summary.videosTotal} videos processed`
            : `${counts.all} ${counts.all === 1 ? "candidate" : "candidates"} · ${summary.videosTotal} ${
                summary.videosTotal === 1 ? "video" : "videos"
              }`}
        </span>
        {counts.all > 0 ? (
          <span className="search-row__review">
            <span className="mini-bar">
              <span style={{ width: percent(reviewed / counts.all) }} />
            </span>
            {reviewed} / {counts.all} reviewed
          </span>
        ) : null}
        {canManage && (summary.status === "failed" || summary.status === "partial") ? (
          <button type="button" className="btn btn-secondary btn-sm push-right" onClick={onRestart}>
            <Icon name="restart" size={14} />
            Restart
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function DatasetPage({ datasetId }: { datasetId: number }) {
  const session = useSession();
  const data = useApiData((signal) => loadDataset(datasetId, signal), [datasetId]);
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [rerun, setRerun] = useState<Video[] | null>(null);
  const [rerunBusy, setRerunBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toast, setToast] = useState("");

  const anyActive = data.data
    ? [...data.data.summaries.values()].some((summary) => isActive(summary.status))
    : false;

  const reload = data.reload;
  useEffect(() => {
    if (!anyActive) return undefined;
    const timer = window.setInterval(reload, 3000);
    return () => window.clearInterval(timer);
  }, [anyActive, reload]);

  async function uploadFiles(files: File[]) {
    if (!data.data || files.length === 0) return;
    setActionError(null);
    const notMp4 = files.filter((file) => !file.name.toLowerCase().endsWith(".mp4"));
    if (notMp4.length > 0) {
      setActionError(
        toApiError(new Error(`Only MP4 files can be uploaded (DS-1): ${notMp4.map((f) => f.name).join(", ")}`)),
      );
      return;
    }
    const uploaded: Video[] = [];
    try {
      for (const [index, file] of files.entries()) {
        setUpload({ name: file.name, index: index + 1, total: files.length, fraction: 0 });
        const video = await api.uploadVideo(datasetId, file, (fraction) =>
          setUpload({ name: file.name, index: index + 1, total: files.length, fraction }),
        );
        uploaded.push(video);
      }
    } catch (failure) {
      setActionError(toApiError(failure));
    } finally {
      setUpload(null);
      data.reload();
    }
    if (uploaded.length === 0) return;
    const long = uploaded.filter((video) => (video.duration_seconds ?? 0) > MAX_SECONDS_MVP);
    setToast(
      `${uploaded.length} ${uploaded.length === 1 ? "video" : "videos"} uploaded.` +
        (long.length ? ` ${long.length} longer than 5 minutes: supported, but not validated yet.` : ""),
    );
    // DS-7: existing searches run again on the new videos after confirmation.
    if (data.data.actions.length > 0) {
      setRerun(uploaded.filter((video) => video.status === "ready"));
    }
  }

  async function runExistingSearches(videos: Video[]) {
    if (!data.data) return;
    setRerunBusy(true);
    setActionError(null);
    try {
      const videoIds = videos.map((video) => video.id);
      for (const action of data.data.actions) {
        const adapter = data.data.summaries.get(action.id)?.adapters[0];
        await api.createActionJobs(
          datasetId,
          action.id,
          { video_ids: videoIds, adapter },
          newIdempotencyKey(),
        );
      }
      setToast(`${data.data.actions.length} existing searches queued on the new videos.`);
    } catch (failure) {
      setActionError(toApiError(failure));
    } finally {
      setRerunBusy(false);
      setRerun(null);
      data.reload();
    }
  }

  async function restart(summary: SearchSummary) {
    setActionError(null);
    try {
      for (const job of summary.jobs) {
        if (job.status === "failed") {
          await api.retryJob(job.id);
        }
      }
    } catch (failure) {
      setActionError(toApiError(failure));
    }
    data.reload();
  }

  async function deleteDataset() {
    try {
      await api.deleteProject(datasetId);
      navigate("/");
    } catch (failure) {
      setActionError(toApiError(failure));
      setConfirmDelete(false);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (upload) return;
    void uploadFiles([...event.dataTransfer.files]);
  }

  if (data.loading && !data.data) {
    return (
      <div className="page">
        <Loading label="Loading dataset…" />
      </div>
    );
  }
  if (!data.data) {
    return (
      <div className="page">
        <PageHeader title="Dataset" back={{ href: "#/", label: "Datasets" }} />
        {data.error ? <ErrorNotice error={data.error} onRetry={data.reload} /> : null}
      </div>
    );
  }

  const { project, videos, actions, summaries, candidatesByAction } = data.data;
  const readyVideos = videos.filter((video) => video.status === "ready");
  const meta = `${videos.length} ${videos.length === 1 ? "video" : "videos"} · ${actions.length} ${
    actions.length === 1 ? "search" : "searches"
  } · created ${formatDate(project.created_at)}`;

  return (
    <div className="page page--wide">
      <PageHeader
        back={{ href: "#/", label: "Datasets" }}
        title={project.name}
        subtitle={meta}
        actions={
          session.canManage ? (
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(true)}>
                <Icon name="trash" size={14} />
                Delete
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={readyVideos.length === 0}
                title={readyVideos.length === 0 ? "Upload at least one video first" : undefined}
                onClick={() => navigate(`/datasets/${datasetId}/searches/new`)}
              >
                <Icon name="search" />
                New search
              </button>
            </>
          ) : null
        }
      />

      {data.error ? <ErrorNotice error={data.error} onRetry={data.reload} title="Refresh failed" /> : null}
      {actionError ? <ErrorNotice error={actionError} title="The action failed" /> : null}

      <div className="two-col">
        <section className="stack" aria-labelledby="videos-heading">
          <div className="section-title">
            <h3 id="videos-heading">Videos</h3>
            <span className="muted tabular">{videos.length}</span>
          </div>

          {session.canManage ? (
            <div
              className={dragging ? "dropzone dropzone--active" : "dropzone"}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <Icon name="upload" size={22} className="accent" />
              <div className="dropzone__text">
                <div className="strong">Drop video files here</div>
                <div className="muted small">MP4 only · up to 5 minutes per video · HD 720p or 1080p</div>
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={upload !== null}
                onClick={() => fileInput.current?.click()}
              >
                Choose files
              </button>
              <input
                ref={fileInput}
                type="file"
                accept=".mp4,video/mp4"
                multiple
                hidden
                onChange={(event) => {
                  const files = [...(event.target.files ?? [])];
                  event.target.value = "";
                  void uploadFiles(files);
                }}
              />
            </div>
          ) : null}

          {upload ? (
            <div className="upload-progress">
              <div className="row-between small">
                <span className="row">
                  <Icon name="spinner" spin size={14} className="accent" />
                  Uploading {upload.name}
                  {upload.total > 1 ? ` (${upload.index} of ${upload.total})` : ""}
                </span>
                <span className="muted tabular">{percent(upload.fraction)}</span>
              </div>
              <ProgressBar value={upload.fraction} label={`Upload of ${upload.name}`} />
            </div>
          ) : null}

          {videos.length > 0 ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Duration</th>
                    <th>Resolution</th>
                    <th>Size</th>
                    <th>Uploaded</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.map((video) => (
                    <tr key={video.id}>
                      <td>
                        <span className="row">
                          <Icon name="film" size={15} className="muted" />
                          <span className="truncate" title={video.original_filename}>
                            {video.original_filename}
                          </span>
                          {video.status !== "ready" ? (
                            <span className="chip chip--failed" title={video.error_message ?? undefined}>
                              {video.status}
                            </span>
                          ) : null}
                        </span>
                      </td>
                      <td className="tabular">{formatClock(video.duration_seconds)}</td>
                      <td className="tabular">{formatResolution(video.width, video.height)}</td>
                      <td className="tabular">{formatBytes(video.size_bytes)}</td>
                      <td className="muted">{formatDate(video.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No videos yet">
              {session.canManage
                ? "Upload MP4 videos to start searching this dataset."
                : "An administrator has not uploaded videos yet."}
            </EmptyState>
          )}
        </section>

        <section className="stack" aria-labelledby="searches-heading">
          <div className="section-title">
            <h3 id="searches-heading">Searches</h3>
            <span className="muted tabular">{actions.length}</span>
          </div>
          {actions.length > 0 ? (
            <div className="search-list">
              {[...actions]
                .sort((a, b) => b.id - a.id)
                .map((action) => (
                  <SearchRow
                    key={action.id}
                    datasetId={datasetId}
                    action={action}
                    summary={summaries.get(action.id) ?? summarizeSearch([])}
                    candidates={candidatesByAction.get(action.id) ?? []}
                    canManage={session.canManage}
                    onRestart={() => void restart(summaries.get(action.id) ?? summarizeSearch([]))}
                  />
                ))}
            </div>
          ) : (
            <EmptyState title="No searches yet">
              {session.canManage
                ? readyVideos.length
                  ? "Describe an action in plain language and run it on every video of this dataset."
                  : "Upload a video, then run a search."
                : "Searches launched by an administrator will appear here."}
            </EmptyState>
          )}
          {!session.canManage ? (
            <Notice>Open a finished search to review its candidates.</Notice>
          ) : null}
        </section>
      </div>

      {rerun && rerun.length > 0 ? (
        <Dialog
          title="Run existing searches on the new videos?"
          onClose={() => setRerun(null)}
          actions={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setRerun(null)}>
                Not now
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={rerunBusy}
                onClick={() => void runExistingSearches(rerun)}
              >
                {rerunBusy ? "Queuing…" : `Run ${actions.length} ${actions.length === 1 ? "search" : "searches"}`}
              </button>
            </>
          }
        >
          <p>
            This dataset already has {actions.length} {actions.length === 1 ? "search" : "searches"}. Each one
            will run again with the same prompt on the {rerun.length} new{" "}
            {rerun.length === 1 ? "video" : "videos"} only. Existing results are kept.
          </p>
          <p className="muted small">Processing can take a while; you can leave the page.</p>
        </Dialog>
      ) : null}

      {confirmDelete ? (
        <Dialog
          title={`Delete ${project.name}?`}
          onClose={() => setConfirmDelete(false)}
          actions={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
                Cancel
              </button>
              <button type="button" className="btn btn-danger" onClick={() => void deleteDataset()}>
                Delete dataset
              </button>
            </>
          }
        >
          <p>
            The videos, searches, candidates, review decisions and exports of this dataset are deleted. This
            cannot be undone.
          </p>
        </Dialog>
      ) : null}

      {toast ? <Toast message={toast} onDone={() => setToast("")} /> : null}
    </div>
  );
}
