import { useEffect, useRef, useState } from "react";

import {
  AriaLive,
  EmptyState,
  ErrorNotice,
  Loading,
  ProgressBar,
  StatusChip,
  Timestamp,
} from "../components/ui";
import {
  api,
  candidateClipUrl,
  getStoredToken,
  toApiError,
  videoStreamUrl,
  withAnnotation,
  type ApiError,
} from "../lib/api";
import {
  formatDateTime,
  formatDuration,
  formatScore,
  formatTimestamp,
  percent,
} from "../lib/format";
import { useApiData, useStoredBoolean, useStoredString } from "../lib/hooks";
import type { ActionDefinition, Candidate, Job, Project, Verdict, Video } from "../types";

interface ReviewData {
  project: Project;
  job: Job;
  video: Video | null;
  action: ActionDefinition | null;
  candidates: Candidate[];
}

type Filter = "all" | "unreviewed" | "true_positive" | "false_positive";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Unreviewed" },
  { value: "true_positive", label: "True positives" },
  { value: "false_positive", label: "False positives" },
];

function matchesFilter(candidate: Candidate, filter: Filter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "unreviewed") {
    return candidate.annotation === null;
  }
  return candidate.annotation?.verdict === filter;
}

function verdictLabel(verdict: Verdict): string {
  return verdict === "true_positive" ? "true positive" : "false positive";
}

function chipLabel(candidate: Candidate): string {
  if (!candidate.annotation) {
    return "Unreviewed";
  }
  return candidate.annotation.verdict === "true_positive" ? "TP" : "FP";
}

function clipUnavailableMessage(candidate: Candidate): string {
  if (candidate.clip_status === "pending") {
    return "The preview clip is still being generated.";
  }
  if (candidate.clip_status === "failed") {
    return candidate.clip_error
      ? `Clip extraction failed: ${candidate.clip_error}`
      : "Clip extraction failed.";
  }
  if (candidate.clip_status === "skipped") {
    return "No preview clip was generated for this candidate.";
  }
  return "";
}

function MissingJobNotice({ projectId }: { projectId: number }) {
  return (
    <section className="card">
      <p className="breadcrumb">
        <a href={`#/projects/${projectId}`}>← Back to project</a>
      </p>
      <h1>Choose a job to review</h1>
      <p className="muted">
        Open the project workspace and use <strong>Review candidates</strong> on a succeeded job.
      </p>
      <a className="btn btn--primary" href={`#/projects/${projectId}`}>
        Go to the project
      </a>
    </section>
  );
}

export function ReviewPage({ projectId, jobId }: { projectId: number; jobId: number | null }) {
  if (jobId === null) {
    return <MissingJobNotice projectId={projectId} />;
  }
  return <ReviewWorkspace projectId={projectId} jobId={jobId} />;
}

function ReviewWorkspace({ projectId, jobId }: { projectId: number; jobId: number }) {
  const review = useApiData<ReviewData>(async (signal) => {
    const [project, job, candidates, actions] = await Promise.all([
      api.getProject(projectId, signal),
      api.getJob(jobId, signal),
      api.jobCandidates(jobId, signal),
      api.listActions(projectId, signal),
    ]);
    const video = job.video_id ? await api.getVideo(job.video_id, signal) : null;
    const action = job.action_id
      ? actions.find((candidate) => candidate.id === job.action_id) ?? null
      : null;
    return { project, job, video, action, candidates };
  }, [projectId, jobId]);

  const [savedCandidates, setSavedCandidates] = useState<Record<number, Candidate>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [note, setNote] = useState("");
  const [startInput, setStartInput] = useState("");
  const [endInput, setEndInput] = useState("");
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [saveFeedback, setSaveFeedback] = useState("");
  const [liveMessage, setLiveMessage] = useState("");
  const [reviewer, setReviewer] = useStoredString("vlm-annotate.reviewer", "");
  const [autoAdvance, setAutoAdvance] = useStoredBoolean("vlm-annotate.auto-advance", true);
  const [clipRequested, setClipRequested] = useState(false);
  const [clipError, setClipError] = useState("");
  const [sourceError, setSourceError] = useState("");
  const [hasToken] = useState(() => getStoredToken() !== "");

  const sourceRef = useRef<HTMLVideoElement>(null);
  const clipRef = useRef<HTMLVideoElement>(null);
  const candidateListRef = useRef<HTMLOListElement>(null);
  const selectedButtonRef = useRef<HTMLButtonElement>(null);
  const keyboardHandler = useRef<(event: KeyboardEvent) => void>(() => undefined);

  const candidateSource = review.data?.candidates ?? [];
  const candidates = candidateSource.map(
    (candidate) => savedCandidates[candidate.id] ?? candidate,
  );
  const visible = candidates.filter((candidate) => matchesFilter(candidate, filter));
  const selected = candidates.find((candidate) => candidate.id === selectedId) ?? null;

  const counts: Record<Filter, number> = {
    all: candidates.length,
    unreviewed: candidates.filter((candidate) => candidate.annotation === null).length,
    true_positive: candidates.filter(
      (candidate) => candidate.annotation?.verdict === "true_positive",
    ).length,
    false_positive: candidates.filter(
      (candidate) => candidate.annotation?.verdict === "false_positive",
    ).length,
  };

  const job = review.data?.job ?? null;
  const video = review.data?.video ?? null;
  const jobActive = job?.status === "queued" || job?.status === "running";

  // Poll while the job is still queued/running. Cleared on unmount.
  useEffect(() => {
    if (!jobActive) {
      return;
    }
    const timer = window.setInterval(() => review.reload(), 2000);
    return () => window.clearInterval(timer);
  }, [jobActive, review.reload]);

  // Keep the selection inside the visible list; default to the first unreviewed.
  const visibleKey = visible.map((candidate) => candidate.id).join(",");
  useEffect(() => {
    if (visible.length === 0) {
      if (selectedId !== null) {
        setSelectedId(null);
      }
      return;
    }
    if (selectedId !== null && visible.some((candidate) => candidate.id === selectedId)) {
      return;
    }
    const next = visible.find((candidate) => candidate.annotation === null) ?? visible[0];
    if (next) {
      setSelectedId(next.id);
    }
  }, [visibleKey, selectedId]);

  // Keep the selected row visible inside the (scrollable) candidate list
  // without scrolling the page around it.
  useEffect(() => {
    const button = selectedButtonRef.current;
    const container = candidateListRef.current;
    if (!button || !container) {
      return;
    }
    const buttonRect = button.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    if (buttonRect.top < containerRect.top) {
      container.scrollTop -= containerRect.top - buttonRect.top;
    } else if (buttonRect.bottom > containerRect.bottom) {
      container.scrollTop += buttonRect.bottom - containerRect.bottom;
    }
  }, [selectedId]);

  // Reset the editor fields when another candidate is selected.
  useEffect(() => {
    if (!selected) {
      setNote("");
      setStartInput("");
      setEndInput("");
      return;
    }
    setNote(selected.annotation?.note ?? "");
    setStartInput(
      String(selected.annotation?.corrected_start_seconds ?? selected.start_seconds),
    );
    setEndInput(String(selected.annotation?.corrected_end_seconds ?? selected.end_seconds));
    setCorrectionError(null);
    setSaveError(null);
    setClipRequested(false);
    setClipError("");
    sourceRef.current?.pause();
    // Only the identity of the selected candidate should reset the editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Seek the source player to the padded preview window of the selected clip.
  useEffect(() => {
    const element = sourceRef.current;
    if (!element || !selected) {
      return;
    }
    const seek = () => {
      element.currentTime = Math.max(0, selected.preview_start_seconds);
    };
    if (element.readyState >= 1) {
      seek();
    } else {
      element.addEventListener("loadedmetadata", seek, { once: true });
    }
    return () => element.removeEventListener("loadedmetadata", seek);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Start clip playback once the <video> with the clip source is mounted.
  useEffect(() => {
    if (!clipRequested) {
      return;
    }
    const element = clipRef.current;
    if (!element) {
      return;
    }
    const attempt = element.play();
    if (attempt) {
      void attempt.catch(() => {
        setClipError("The browser blocked autoplay. Press play on the clip player.");
      });
    }
  }, [clipRequested, selectedId]);

  function playSourceWindow() {
    if (!selected) {
      return;
    }
    const element = sourceRef.current;
    if (!element) {
      return;
    }
    element.currentTime = Math.max(0, selected.preview_start_seconds);
    const attempt = element.play();
    if (attempt) {
      void attempt.catch(() => undefined);
    }
  }

  function playClip() {
    if (!selected) {
      return;
    }
    if (selected.clip_status !== "ready") {
      setClipError(`${clipUnavailableMessage(selected)} Playing the source preview instead.`);
      playSourceWindow();
      return;
    }
    setClipError("");
    sourceRef.current?.pause();
    setClipRequested(true);
    const element = clipRef.current;
    if (element) {
      element.currentTime = 0;
      const attempt = element.play();
      if (attempt) {
        void attempt.catch(() => undefined);
      }
    }
  }

  function togglePlayback() {
    if (clipRequested && clipRef.current) {
      if (clipRef.current.paused) {
        void clipRef.current.play().catch(() => undefined);
      } else {
        clipRef.current.pause();
      }
      return;
    }
    const element = sourceRef.current;
    if (!element) {
      return;
    }
    if (element.paused) {
      void element.play().catch(() => undefined);
    } else {
      element.pause();
    }
  }

  function step(direction: 1 | -1) {
    if (visible.length === 0) {
      return;
    }
    const index = selected ? visible.findIndex((candidate) => candidate.id === selected.id) : -1;
    const base = index === -1 ? 0 : index;
    const nextIndex = (base + direction + visible.length) % visible.length;
    const next = visible[nextIndex];
    if (next) {
      setSelectedId(next.id);
    }
  }

  function readBoundaries():
    | { start: number; end: number; changed: boolean }
    | { error: string } {
    if (!selected) {
      return { error: "Select a candidate first." };
    }
    if (!startInput.trim() || !endInput.trim()) {
      return { error: "Enter both a start and an end time." };
    }
    const start = Number(startInput);
    const end = Number(endInput);
    if (!Number.isFinite(start) || !Number.isFinite(end)) {
      return { error: "Start and end must be numbers (seconds)." };
    }
    if (start < 0) {
      return { error: "Start must be zero or greater." };
    }
    if (end <= start) {
      return { error: "End must be greater than start." };
    }
    const duration = video?.duration_seconds ?? null;
    if (duration !== null && end > duration + 0.001) {
      return {
        error: `End must be within the video duration (${formatDuration(duration)}).`,
      };
    }
    const changed =
      Math.abs(start - selected.start_seconds) > 1e-6 ||
      Math.abs(end - selected.end_seconds) > 1e-6;
    return { start, end, changed };
  }

  function nextUnreviewed(list: Candidate[], fromId: number): Candidate | null {
    const index = list.findIndex((candidate) => candidate.id === fromId);
    if (index === -1) {
      return list.find((candidate) => candidate.annotation === null) ?? null;
    }
    const ordered = [...list.slice(index + 1), ...list.slice(0, index + 1)];
    return ordered.find((candidate) => candidate.annotation === null) ?? null;
  }

  async function save(verdict: Verdict) {
    if (!selected || saving) {
      return;
    }
    const boundaries = readBoundaries();
    if ("error" in boundaries) {
      setCorrectionError(boundaries.error);
      setLiveMessage(`Could not save: ${boundaries.error}`);
      return;
    }
    setCorrectionError(null);
    setSaveError(null);
    setSaving(true);
    try {
      const updated = await api.upsertAnnotation(selected.id, {
        verdict,
        note: note.trim(),
        reviewer: reviewer.trim() || "anonymous",
        ...(boundaries.changed
          ? {
              corrected_start_seconds: boundaries.start,
              corrected_end_seconds: boundaries.end,
            }
          : {}),
      });
      setSavedCandidates((current) => ({ ...current, [updated.id]: updated }));
      const updatedList = candidates.map((candidate) =>
        candidate.id === updated.id ? updated : candidate,
      );

      let message = `Saved ${verdictLabel(verdict)} for rank ${updated.rank}.`;
      if (autoAdvance) {
        const next = nextUnreviewed(updatedList, updated.id);
        if (next) {
          if (!matchesFilter(next, filter)) {
            setFilter("all");
          }
          setSelectedId(next.id);
          message += ` Moved to rank ${next.rank}.`;
        } else {
          message += " All candidates are reviewed.";
        }
      }
      setSaveFeedback(message);
      setLiveMessage(message);
    } catch (failure) {
      const apiError = toApiError(failure);
      setSaveError(apiError);
      setLiveMessage(`Could not save: ${apiError.message}`);
    } finally {
      setSaving(false);
    }
  }

  async function resetAnnotation() {
    if (!selected || saving) {
      return;
    }
    setSaveError(null);
    setSaving(true);
    try {
      await api.deleteAnnotation(selected.id);
      const updated = withAnnotation(selected, null);
      setSavedCandidates((current) => ({ ...current, [updated.id]: updated }));
      setStartInput(String(updated.start_seconds));
      setEndInput(String(updated.end_seconds));
      setNote("");
      setCorrectionError(null);
      const message = `Rank ${updated.rank} reset to unreviewed.`;
      setSaveFeedback(message);
      setLiveMessage(message);
    } catch (failure) {
      const apiError = toApiError(failure);
      setSaveError(apiError);
      setLiveMessage(`Could not reset: ${apiError.message}`);
    } finally {
      setSaving(false);
    }
  }

  // Keyboard shortcuts are registered once and dispatch through a ref so they
  // always see the latest selection and form values.
  keyboardHandler.current = (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }
    const target = event.target;
    if (target instanceof HTMLElement) {
      const tag = target.tagName;
      // Never steal keys while the user is typing.
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target.isContentEditable
      ) {
        return;
      }
      // Space must keep activating the focused control.
      if (
        event.key === " " &&
        (tag === "BUTTON" || tag === "A" || tag === "SUMMARY")
      ) {
        return;
      }
    }
    if (event.key === "j" || event.key === "J") {
      event.preventDefault();
      void save("true_positive");
    } else if (event.key === "f" || event.key === "F") {
      event.preventDefault();
      void save("false_positive");
    } else if (event.key === " ") {
      event.preventDefault();
      togglePlayback();
    } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      step(-1);
    }
  };

  useEffect(() => {
    const listener = (event: KeyboardEvent) => keyboardHandler.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  if (!review.data && review.loading) {
    return <Loading label="Loading review…" />;
  }

  if (!review.data) {
    return (
      <section className="card">
        <p className="breadcrumb">
          <a href={`#/projects/${projectId}`}>← Back to project</a>
        </p>
        <h1>Review</h1>
        {review.error ? (
          <ErrorNotice
            error={review.error}
            onRetry={review.reload}
            title="The review could not be loaded"
          />
        ) : (
          <Loading label="Reloading review…" />
        )}
      </section>
    );
  }

  const { project, action } = review.data;
  const unreviewed = counts.unreviewed;

  return (
    <>
      <AriaLive message={liveMessage} />

      <header className="page-head review-head">
        <div>
          <p className="breadcrumb">
            <a href={`#/projects/${projectId}`}>← {project.name}</a>
          </p>
          <h1>
            Review candidates <span className="muted">· Job #{jobId}</span>
          </h1>
          <p className="meta">
            {action ? (
              <>
                Action: <strong>{action.name}</strong> ·{" "}
              </>
            ) : (
              "Action: — · "
            )}
            Adapter {job?.adapter_name ?? "—"}
            {job?.adapter_version ? ` v${job.adapter_version}` : ""}
            {video ? ` · ${video.original_filename}` : ""}
            {video ? ` (${formatDuration(video.duration_seconds)})` : ""}
          </p>
          <p className="row">
            {job ? <StatusChip status={job.status} /> : null}
            <span className="meta">Job #{jobId}</span>
          </p>
        </div>
        <p className="review-counter">
          <strong>{unreviewed}</strong> unreviewed of {counts.all}
        </p>
      </header>

      {job?.adapter_name === "mock" ? (
        <div className="banner banner--mock" role="status">
          <div className="banner__content">
            <strong>MOCK CANDIDATES — no video pixels were analysed.</strong>
            <p>
              This job used the deterministic <code>mock</code> adapter. Timestamps and scores are
              synthetic; the export manifest flags them with{" "}
              <code>provenance.mock: true</code>.
            </p>
          </div>
        </div>
      ) : null}

      {job?.status === "failed" || job?.status === "canceled" ? (
        <div className="banner banner--danger" role="alert">
          <div className="banner__content">
            <strong>Job #{job.id} {job.status}.</strong>
            <p>
              {job.error_code ? <code className="error-code">{job.error_code}</code> : null}{" "}
              {job.error_message ?? "No candidates are available for this job."}
            </p>
          </div>
          <a className="btn btn--ghost btn--small" href={`#/projects/${projectId}`}>
            Back to project
          </a>
        </div>
      ) : null}

      {jobActive ? (
        <div className="banner banner--info" role="status">
          <div className="banner__content">
            <strong>
              Job #{job?.id} is {job?.status} — {percent(job?.progress ?? 0)}
            </strong>
            <p>Candidates appear here automatically when the job succeeds.</p>
            <ProgressBar value={job?.progress ?? 0} label={`Job ${jobId} progress`} />
          </div>
        </div>
      ) : null}

      {review.error ? (
        <ErrorNotice
          error={review.error}
          onRetry={review.reload}
          title="Showing the last loaded review — refresh failed"
        />
      ) : null}

      <div className="review-grid">
        <section className="card player-panel" aria-labelledby="source-heading">
          <div className="panel__head">
            <h2 id="source-heading">Source video</h2>
            <p className="muted">
              {selected ? (
                <>
                  Preview window{" "}
                  <Timestamp seconds={selected.preview_start_seconds} /> –{" "}
                  <Timestamp seconds={selected.preview_end_seconds} />
                </>
              ) : (
                "Select a candidate to jump to its preview window."
              )}
            </p>
          </div>

          {video ? (
            <video
              ref={sourceRef}
              className="video-player"
              controls
              preload="metadata"
              playsInline
              src={videoStreamUrl(video.id)}
              onError={() =>
                setSourceError(
                  "The source video could not be loaded. Check that the file still exists on the server.",
                )
              }
            />
          ) : (
            <EmptyState title="Source video unavailable">
              <p>The job has no video attached, or the video was deleted.</p>
            </EmptyState>
          )}

          {sourceError ? (
            <p className="error-text" role="alert">
              {sourceError}
            </p>
          ) : null}

          {hasToken ? (
            <p className="field__hint field__hint--warn">
              An API token is stored in this browser. Media elements cannot send an{" "}
              <code>Authorization</code> header, so a token-protected deployment may reject video
              playback with HTTP 401. Remove the token to use the open development server.
            </p>
          ) : null}

          <div className="clip-block">
            <div className="clip-block__head">
              <h3>Generated clip</h3>
              <StatusChip status={selected?.clip_status ?? "pending"} />
            </div>

            {selected ? (
              <>
                {selected.clip_status === "ready" && clipRequested ? (
                  <video
                    ref={clipRef}
                    className="video-player video-player--clip"
                    controls
                    preload="auto"
                    playsInline
                    src={candidateClipUrl(selected.id)}
                    onError={() =>
                      setClipError(
                        "The clip file could not be loaded. Play the same window in the source player instead.",
                      )
                    }
                  />
                ) : (
                  <p className="meta">
                    {selected.clip_status === "ready"
                      ? `Clip ready · ${formatTimestamp(selected.preview_start_seconds)} – ${formatTimestamp(selected.preview_end_seconds)}`
                      : clipUnavailableMessage(selected)}
                  </p>
                )}

                <div className="row">
                  <button
                    type="button"
                    className="btn btn--primary btn--small"
                    onClick={playClip}
                    disabled={saving}
                  >
                    Play clip
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--small"
                    onClick={playSourceWindow}
                  >
                    Play in source
                  </button>
                </div>

                {clipError ? (
                  <p className="error-text" role="alert">
                    {clipError}
                  </p>
                ) : null}
              </>
            ) : (
              <p className="meta">No candidate selected.</p>
            )}
          </div>
        </section>

        <aside className="card candidate-panel" aria-labelledby="candidates-heading">
          <div className="panel__head">
            <h2 id="candidates-heading">Candidates</h2>
            <p className="muted">
              <strong>{unreviewed}</strong> unreviewed of {counts.all} · ordered by rank
            </p>
          </div>

          <div className="filter-tabs" role="group" aria-label="Filter candidates by review state">
            {FILTERS.map((filterOption) => (
              <button
                key={filterOption.value}
                type="button"
                className={
                  filter === filterOption.value ? "filter-tab filter-tab--active" : "filter-tab"
                }
                aria-pressed={filter === filterOption.value}
                onClick={() => setFilter(filterOption.value)}
              >
                {filterOption.label}
                <span className="filter-tab__count">{counts[filterOption.value]}</span>
              </button>
            ))}
          </div>

          {candidates.length === 0 ? (
            <EmptyState title="No candidates">
              <p>
                {jobActive
                  ? "The job is still running. Candidates will appear here automatically."
                  : "This job did not produce any candidates."}
              </p>
              <a className="btn btn--ghost btn--small" href={`#/projects/${projectId}`}>
                Back to project
              </a>
            </EmptyState>
          ) : visible.length === 0 ? (
            <EmptyState title="No candidates match this filter">
              <button type="button" className="btn btn--ghost btn--small" onClick={() => setFilter("all")}>
                Show all candidates
              </button>
            </EmptyState>
          ) : (
            <ol className="candidate-list" ref={candidateListRef}>
              {visible.map((candidate) => {
                const isSelected = candidate.id === selectedId;
                return (
                  <li key={candidate.id}>
                    <button
                      ref={isSelected ? selectedButtonRef : undefined}
                      type="button"
                      className={isSelected ? "candidate candidate--selected" : "candidate"}
                      aria-current={isSelected ? "true" : undefined}
                      onClick={() => setSelectedId(candidate.id)}
                    >
                      <span className="candidate__top">
                        <span className="candidate__rank">Rank {candidate.rank}</span>
                        <StatusChip
                          status={candidate.annotation?.verdict ?? "unreviewed"}
                          label={chipLabel(candidate)}
                        />
                      </span>
                      <span className="candidate__times">
                        <Timestamp seconds={candidate.start_seconds} />
                        <span aria-hidden="true"> – </span>
                        <Timestamp seconds={candidate.end_seconds} />
                      </span>
                      <span className="candidate__meta">
                        Score {formatScore(candidate.score)} · Clip {candidate.clip_status}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </aside>

        <section className="card label-panel" aria-labelledby="label-heading">
          <div className="panel__head">
            <h2 id="label-heading">Label candidate</h2>
            <p className="muted">
              Reviewing is manual: J or F saves the verdict; unreviewed candidates have no verdict.
            </p>
          </div>

          {selected ? (
            <>
              <div className="candidate-summary">
                <span className="badge">Rank {selected.rank}</span>
                <StatusChip status={selected.review_state} />
                <span className="meta">
                  Score {formatScore(selected.score)} · Clip {selected.clip_status}
                </span>
              </div>

              <p className="model-notes">
                <span className="model-notes__label">Model notes</span>
                {selected.model_notes || "No model notes provided."}
              </p>

              {selected.annotation ? (
                <dl className="annotation-details">
                  <div>
                    <dt>Verdict</dt>
                    <dd>
                      <StatusChip
                        status={selected.annotation.verdict}
                        label={
                          selected.annotation.verdict === "true_positive"
                            ? "True positive"
                            : "False positive"
                        }
                      />
                    </dd>
                  </div>
                  <div>
                    <dt>Reviewer</dt>
                    <dd>{selected.annotation.reviewer || "anonymous"}</dd>
                  </div>
                  <div>
                    <dt>Reviewed</dt>
                    <dd>{formatDateTime(selected.annotation.updated_at)}</dd>
                  </div>
                  {selected.annotation.corrected_start_seconds !== null &&
                  selected.annotation.corrected_end_seconds !== null ? (
                    <div>
                      <dt>Corrected</dt>
                      <dd>
                        <Timestamp seconds={selected.annotation.corrected_start_seconds} /> –{" "}
                        <Timestamp seconds={selected.annotation.corrected_end_seconds} />
                      </dd>
                    </div>
                  ) : null}
                  {selected.annotation.note ? (
                    <div>
                      <dt>Note</dt>
                      <dd>{selected.annotation.note}</dd>
                    </div>
                  ) : null}
                </dl>
              ) : null}

              <div className="verdict-buttons">
                <button
                  type="button"
                  className={
                    selected.annotation?.verdict === "true_positive"
                      ? "btn btn--tp btn--large btn--verdict-active"
                      : "btn btn--tp btn--large"
                  }
                  aria-pressed={selected.annotation?.verdict === "true_positive"}
                  disabled={saving}
                  onClick={() => void save("true_positive")}
                >
                  <span>True positive</span>
                  <kbd>J</kbd>
                </button>
                <button
                  type="button"
                  className={
                    selected.annotation?.verdict === "false_positive"
                      ? "btn btn--fp btn--large btn--verdict-active"
                      : "btn btn--fp btn--large"
                  }
                  aria-pressed={selected.annotation?.verdict === "false_positive"}
                  disabled={saving}
                  onClick={() => void save("false_positive")}
                >
                  <span>False positive</span>
                  <kbd>F</kbd>
                </button>
              </div>

              {selected.annotation ? (
                <button
                  type="button"
                  className="btn btn--ghost btn--small"
                  disabled={saving}
                  onClick={() => void resetAnnotation()}
                >
                  Reset to unreviewed
                </button>
              ) : null}

              <div className="form-grid">
                <div className="field field--full">
                  <label htmlFor="review-note">Note</label>
                  <textarea
                    id="review-note"
                    name="note"
                    rows={2}
                    maxLength={2000}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder="Optional note stored with the annotation"
                  />
                </div>
                <div className="field">
                  <label htmlFor="reviewer">Reviewer</label>
                  <input
                    id="reviewer"
                    name="reviewer"
                    type="text"
                    maxLength={100}
                    value={reviewer}
                    onChange={(event) => setReviewer(event.target.value)}
                    placeholder="Your name"
                  />
                  <p className="field__hint">Kept in this browser for the next annotation.</p>
                </div>
              </div>

              <fieldset className="fieldset">
                <legend>Correct the boundaries (seconds)</legend>
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="corrected-start">Start</label>
                    <input
                      id="corrected-start"
                      name="corrected-start"
                      type="number"
                      step="0.001"
                      min="0"
                      value={startInput}
                      onChange={(event) => setStartInput(event.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="corrected-end">End</label>
                    <input
                      id="corrected-end"
                      name="corrected-end"
                      type="number"
                      step="0.001"
                      min="0"
                      value={endInput}
                      onChange={(event) => setEndInput(event.target.value)}
                    />
                  </div>
                </div>
                <p className="field__hint">
                  Pre-filled from the model proposal. If either value changes, both corrected
                  timestamps are saved with the annotation. Start must be before end and end must
                  fall inside the video duration.
                </p>
                {correctionError ? (
                  <p className="error-text" role="alert">
                    {correctionError}
                  </p>
                ) : null}
              </fieldset>

              {saveError ? (
                <p className="error-text" role="alert">
                  <code className="error-code">{saveError.code}</code> {saveError.message}
                </p>
              ) : null}

              {saveFeedback ? <p className="save-feedback">{saveFeedback}</p> : null}

              <div className="checkbox-field">
                <input
                  id="auto-advance"
                  name="auto-advance"
                  type="checkbox"
                  checked={autoAdvance}
                  onChange={(event) => setAutoAdvance(event.target.checked)}
                />
                <label htmlFor="auto-advance">Auto-advance to the next unreviewed candidate</label>
              </div>

              <details className="shortcuts">
                <summary>Keyboard shortcuts</summary>
                <ul>
                  <li>
                    <kbd>J</kbd> true positive
                  </li>
                  <li>
                    <kbd>F</kbd> false positive
                  </li>
                  <li>
                    <kbd>Space</kbd> play/pause the source or clip player
                  </li>
                  <li>
                    <kbd>←</kbd> / <kbd>→</kbd> previous / next visible candidate
                  </li>
                </ul>
                <p className="field__hint">
                  Shortcuts are ignored while typing in a field or when a button or link has focus.
                </p>
              </details>
            </>
          ) : (
            <EmptyState title="No candidate selected">
              <p>
                {candidates.length === 0
                  ? jobActive
                    ? "The job is still running."
                    : "This job did not produce candidates."
                  : "Select a candidate from the list, or change the filter."}
              </p>
            </EmptyState>
          )}
        </section>
      </div>
    </>
  );
}
