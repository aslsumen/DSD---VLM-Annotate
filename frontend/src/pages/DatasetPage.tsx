/**
 * Dataset page (DS-1, DS-2, DS-4, DS-7, PR-1, DET-3, REV-4, NFR-9;
 * Design Description v1.2, 5.3): videos with upload, and one row per search.
 */
import type { DragEvent } from "react";
import { useRef, useState } from "react";

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
import { useApiData, useSearchPolling } from "../lib/hooks";
import { navigate } from "../lib/router";
import {
  deleteSearch,
  findPendingSearches,
  runPendingSearches,
  type PendingSearch,
} from "../lib/operations";
import {
  countReview,
  isActive,
  summarizeSearch,
  unprocessedVideos,
  type SearchSummary,
} from "../lib/search";
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
  onDelete,
}: {
  datasetId: number;
  action: ActionDefinition;
  summary: SearchSummary;
  candidates: Candidate[];
  canManage: boolean;
  onRestart: () => void;
  onDelete: () => void;
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
        {canManage ? (
          <span className="search-row__actions">
            {summary.status === "failed" || summary.status === "partial" ? (
              <button type="button" className="btn btn-secondary btn-sm" onClick={onRestart}>
                <Icon name="restart" size={14} />
                Restart
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-icon"
              onClick={onDelete}
              aria-label={`Delete search ${action.name}`}
              title="Delete search"
            >
              <Icon name="trash" size={14} />
            </button>
          </span>
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
  const [deletingVideo, setDeletingVideo] = useState<Video | null>(null);
  const [deletingSearch, setDeletingSearch] = useState<ActionDefinition | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [pending, setPending] = useState<PendingSearch[] | null>(null);
  const [pendingBusy, setPendingBusy] = useState(false);
  const [toast, setToast] = useState("");

  const anyActive = data.data
    ? [...data.data.summaries.values()].some((summary) => isActive(summary.status))
    : false;

  const reload = data.reload;
  useSearchPolling(data, anyActive, 3000);

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

  async function removeVideo(video: Video) {
    setDeleteBusy(true);
    setActionError(null);
    try {
      await api.deleteVideo(video.id);
      setToast(`${video.original_filename} deleted.`);
    } catch (failure) {
      setActionError(toApiError(failure));
    } finally {
      setDeleteBusy(false);
      setDeletingVideo(null);
      reload();
    }
  }

  async function removeSearch(action: ActionDefinition) {
    setDeleteBusy(true);
    setActionError(null);
    try {
      await deleteSearch(datasetId, action.id);
      setToast(`Search “${action.name}” deleted.`);
    } catch (failure) {
      setActionError(toApiError(failure));
    } finally {
      setDeleteBusy(false);
      setDeletingSearch(null);
      reload();
    }
  }

  async function openPending() {
    if (!data.data) return;
    setPendingBusy(true);
    setActionError(null);
    try {
      setPending(await findPendingSearches(datasetId, data.data.actions, data.data.videos));
    } catch (failure) {
      setActionError(toApiError(failure));
    } finally {
      setPendingBusy(false);
    }
  }

  async function confirmPending(items: PendingSearch[]) {
    setPendingBusy(true);
    setActionError(null);
    try {
      const queued = await runPendingSearches(datasetId, items);
      setToast(`${queued} ${queued === 1 ? "job" : "jobs"} queued.`);
    } catch (failure) {
      setActionError(toApiError(failure));
    } finally {
      setPendingBusy(false);
      setPending(null);
      reload();
    }
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
  // Estimate from the loaded jobs; the dialog re-reads the API before queuing.
  const pendingEstimate = actions.reduce(
    (sum, action) => sum + unprocessedVideos(videos, summaries.get(action.id)?.jobs ?? []).length,
    0,
  );
  const allCandidates = [...candidatesByAction.values()].flat();
  const videoImpact = (video: Video) => {
    const list = allCandidates.filter((candidate) => candidate.video_id === video.id);
    return { candidates: list.length, reviewed: list.filter((candidate) => candidate.annotation).length };
  };
  const searchImpact = (action: ActionDefinition) => {
    const list = candidatesByAction.get(action.id) ?? [];
    return { candidates: list.length, reviewed: list.filter((candidate) => candidate.annotation).length };
  };

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
              {actions.length > 0 ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={pendingEstimate === 0 || pendingBusy}
                  title={
                    pendingEstimate === 0
                      ? "Every search has already run on every ready video"
                      : "Run every search on the videos it has not processed yet"
                  }
                  onClick={() => void openPending()}
                >
                  <Icon name="restart" size={14} />
                  Run searches on new videos{pendingEstimate > 0 ? ` (${pendingEstimate})` : ""}
                </button>
              ) : null}
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
                    {session.canManage ? <th className="right">Actions</th> : null}
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
                      {session.canManage ? (
                        <td className="right">
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm btn-icon"
                            onClick={() => setDeletingVideo(video)}
                            aria-label={`Delete ${video.original_filename}`}
                            title="Delete video"
                          >
                            <Icon name="trash" size={14} />
                          </button>
                        </td>
                      ) : null}
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
                    onDelete={() => setDeletingSearch(action)}
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

      {deletingVideo ? (
        <Dialog
          title={`Delete ${deletingVideo.original_filename}?`}
          onClose={() => setDeletingVideo(null)}
          actions={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setDeletingVideo(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={deleteBusy}
                onClick={() => void removeVideo(deletingVideo)}
              >
                {deleteBusy ? "Deleting…" : "Delete video"}
              </button>
            </>
          }
        >
          <p>
            The video file is removed from the dataset, with its processing jobs, candidates and preview clips.
          </p>
          {videoImpact(deletingVideo).reviewed > 0 ? (
            <Notice tone="warning" title="Review decisions will be lost">
              {videoImpact(deletingVideo).reviewed} of {videoImpact(deletingVideo).candidates} candidates of this
              video were already reviewed. Their decisions are deleted and will not be exported.
            </Notice>
          ) : (
            <p className="muted small">
              {videoImpact(deletingVideo).candidates} candidates, none reviewed. This cannot be undone.
            </p>
          )}
        </Dialog>
      ) : null}

      {deletingSearch ? (
        <Dialog
          title={`Delete the search “${deletingSearch.name}”?`}
          onClose={() => setDeletingSearch(null)}
          actions={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setDeletingSearch(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={deleteBusy}
                onClick={() => void removeSearch(deletingSearch)}
              >
                {deleteBusy ? "Deleting…" : "Delete search"}
              </button>
            </>
          }
        >
          <p>
            The prompt “{deletingSearch.description}” is removed from the dataset. Queued and running jobs of this
            search are canceled first.
          </p>
          {searchImpact(deletingSearch).reviewed > 0 ? (
            <Notice tone="warning" title="Review decisions will be lost">
              Its {searchImpact(deletingSearch).candidates} candidates are deleted, including{" "}
              {searchImpact(deletingSearch).reviewed} already reviewed. They will not be exported. This cannot be
              undone.
            </Notice>
          ) : (
            <p className="muted small">
              Its {searchImpact(deletingSearch).candidates} candidates and their preview clips are deleted too. This
              cannot be undone.
            </p>
          )}
        </Dialog>
      ) : null}

      {pending ? (
        <Dialog
          title={pending.length ? "Run searches on new videos?" : "Nothing to run"}
          onClose={() => setPending(null)}
          actions={
            pending.length ? (
              <>
                <button type="button" className="btn btn-ghost" onClick={() => setPending(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={pendingBusy}
                  onClick={() => void confirmPending(pending)}
                >
                  {pendingBusy
                    ? "Queuing…"
                    : `Queue ${pending.reduce((sum, item) => sum + item.videos.length, 0)} jobs`}
                </button>
              </>
            ) : (
              <button type="button" className="btn btn-secondary" onClick={() => setPending(null)}>
                Close
              </button>
            )
          }
        >
          {pending.length ? (
            <>
              <p>
                Each search runs with the same prompt on the videos it has not processed yet. Existing results are
                kept (DS-7). Failed videos are not included: use Restart on the search.
              </p>
              <ul className="pending-list">
                {pending.map((item) => (
                  <li key={item.action.id}>
                    <span className="strong">{item.action.name}</span>
                    <span className="muted small">
                      {item.videos.length} {item.videos.length === 1 ? "video" : "videos"}:{" "}
                      {item.videos.map((video) => video.original_filename).join(", ")}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="muted small">Processing can take a while; you can leave the page.</p>
            </>
          ) : (
            <p>Every search has already run on every ready video of this dataset.</p>
          )}
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
