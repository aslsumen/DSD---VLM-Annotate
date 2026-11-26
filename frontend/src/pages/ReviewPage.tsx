/**
 * Review screen (REV-1 to REV-5, DET-2, DET-4, NFR-7; Design Description v1.2, 5.4).
 *
 * - One list with the candidates of every video of the search, filtered by status
 *   only (no video filter, NFR-7), sortable by confidence or by time.
 * - The full video plays from the selected candidate; the reviewer can move before
 *   and after it (REV-1). A clip view is kept for quick checks.
 * - Start/end are adjusted on a zoomed track or with ±0.5 s steppers (REV-2); the
 *   model times stay stored for the timestamp-precision KPI (NFR-5).
 * - Accept / reject is final (REV-3): decided candidates are read-only.
 * - One reviewer per video (REV-5): the first person who decides a candidate of a
 *   video owns it; others see that video read-only. Enforced in the client until the
 *   backend lock (Video.reviewer_id) exists.
 */
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from "react";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import {
  AriaLive,
  Dialog,
  EmptyState,
  ErrorNotice,
  Icon,
  Loading,
  Notice,
  ReviewChip,
} from "../components/ui";
import { api, candidateClipUrl, toApiError, videoStreamUrl, withAnnotation, type ApiError } from "../lib/api";
import { formatClock, formatScore, formatTimestamp, percent } from "../lib/format";
import { useApiData, useStoredBoolean, useStoredString } from "../lib/hooks";
import {
  countReview,
  finalBounds,
  reviewStatus,
  summarizeSearch,
  videoReviewer,
  type ReviewStatus,
} from "../lib/search";
import { reviewInterval, reviewSeconds } from "../lib/reviewBounds";
import { useSession, type ReviewDraft } from "../lib/session";
import type { Candidate, Video } from "../types";

type Filter = "all" | ReviewStatus;
type Sort = "confidence" | "time";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Unreviewed" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Rejected" },
];

const SHORTCUTS = [
  ["A", "Accept"],
  ["R", "Reject"],
  ["N", "Next unreviewed"],
  ["↓ / ↑", "Next / previous candidate"],
  ["Space", "Play / pause"],
  ["?", "Show shortcuts"],
] as const;

const STEP = 0.5;

async function load(projectId: number, actionId: number, signal: AbortSignal) {
  const [project, actions, videos, candidates, jobs] = await Promise.all([
    api.getProject(projectId, signal),
    api.listActions(projectId, signal),
    api.listVideos(projectId, signal),
    api.projectCandidates(projectId, { actionId }, signal),
    api.listJobs({ projectId, actionId, limit: 200 }, signal),
  ]);
  return {
    project,
    action: actions.find((item) => item.id === actionId) ?? null,
    videos,
    candidates,
    adapters: summarizeSearch(jobs).adapters,
  };
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
}

export function ReviewPage({ datasetId, searchId }: { datasetId: number; searchId: number }) {
  const session = useSession();
  const data = useApiData((signal) => load(datasetId, searchId, signal), [datasetId, searchId]);

  const [saved, setSaved] = useState<Record<number, Candidate>>({});
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("confidence");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [, refreshDraft] = useReducer((version: number) => version + 1, 0);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<{ id: number; error: ApiError } | null>(null);
  const [inputError, setInputError] = useState("");
  const [live, setLive] = useState("");
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [view, setView] = useState<"full" | "clip">("full");
  const [currentTime, setCurrentTime] = useState(0);
  const [paused, setPaused] = useState(true);
  const [autoAdvance, setAutoAdvance] = useStoredBoolean("vlm-annotate.auto-advance", true);
  const [openReviewer, setOpenReviewer] = useStoredString("vlm-annotate.reviewer", "");

  const videoRef = useRef<HTMLVideoElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef<"start" | "end" | null>(null);
  const keyHandler = useRef<(event: KeyboardEvent) => void>(() => undefined);

  const reviewer = session.user ? session.reviewerName : openReviewer.trim() || "anonymous";

  const candidates = useMemo(
    () => (data.data?.candidates ?? []).map((candidate) => saved[candidate.id] ?? candidate),
    [data.data, saved],
  );
  const videoById = useMemo(
    () => new Map<number, Video>((data.data?.videos ?? []).map((video) => [video.id, video])),
    [data.data],
  );
  const counts = countReview(candidates);
  const videoCount = new Set(candidates.map((candidate) => candidate.video_id)).size;

  const ordered = useMemo(() => {
    const list = [...candidates];
    if (sort === "confidence") {
      list.sort((a, b) => b.score - a.score || a.video_id - b.video_id || a.start_seconds - b.start_seconds);
    } else {
      list.sort((a, b) => a.video_id - b.video_id || a.start_seconds - b.start_seconds);
    }
    return list;
  }, [candidates, sort]);
  const visible = ordered.filter((candidate) => filter === "all" || reviewStatus(candidate) === filter);
  const selected = candidates.find((candidate) => candidate.id === selectedId) ?? null;
  const selectedVideo = selected ? videoById.get(selected.video_id) ?? null : null;
  const duration = selectedVideo?.duration_seconds ?? (selected ? selected.preview_end_seconds : 0);

  const owner = selected ? videoReviewer(candidates, selected.video_id) : null;
  const lockedByOther = Boolean(owner && owner !== reviewer && session.user);
  const decided = Boolean(selected?.annotation);
  const readOnly = decided || lockedByOther;

  const drafts = session.reviewDrafts;
  const draftKey = (id: number) => `${datasetId}/${searchId}/${id}`;
  const draft = selected && !readOnly ? drafts.get(draftKey(selected.id)) : undefined;

  const bounds = selected ? finalBounds(selected) : { start: 0, end: 0 };
  const startText = draft?.startText ?? String(bounds.start);
  const endText = draft?.endText ?? String(bounds.end);
  const note = draft?.note ?? selected?.annotation?.note ?? "";
  const startValue = reviewSeconds(startText) ?? bounds.start;
  const endValue = reviewSeconds(endText) ?? bounds.end;
  const editingDisabled = readOnly || (selected !== null && savingId === selected.id);

  function editDraft(changes: Partial<ReviewDraft>) {
    if (!selected || editingDisabled) return;
    drafts.set(draftKey(selected.id), { startText, endText, note, ...changes });
    setInputError("");
    refreshDraft();
  }

  // Return to an unsubmitted edit when the same user resumes this search.
  useEffect(() => {
    if (selectedId !== null || ordered.length === 0) return;
    const first = ordered.find((candidate) => !candidate.annotation
      && drafts.has(`${datasetId}/${searchId}/${candidate.id}`))
      ?? ordered.find((candidate) => !candidate.annotation) ?? ordered[0];
    setSelectedId(first.id);
  }, [ordered, selectedId, drafts, datasetId, searchId]);

  // Reset the editor when the selection changes.
  useEffect(() => {
    if (!selected) return;
    setSaveError(null);
    setInputError("");
    if (draft) setLive("Unsaved review edits restored.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id]);

  // REV-1: jump the full video to the candidate's start.
  useEffect(() => {
    const element = videoRef.current;
    if (!element || !selected || view !== "full") return undefined;
    const target = Math.max(0, finalBounds(selected).start);
    const seek = () => {
      element.currentTime = target;
    };
    if (element.readyState >= 1) seek();
    else element.addEventListener("loadedmetadata", seek, { once: true });
    return () => element.removeEventListener("loadedmetadata", seek);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id, selected?.video_id, view]);

  const select = useCallback((candidate: Candidate | undefined) => {
    if (candidate) setSelectedId(candidate.id);
  }, []);

  function step(delta: number) {
    if (!selected) return;
    const index = visible.findIndex((candidate) => candidate.id === selected.id);
    select(visible[index + delta] ?? visible[index]);
  }

  function nextUnreviewed(fromId = selected?.id) {
    const index = ordered.findIndex((candidate) => candidate.id === fromId);
    const after = [...ordered.slice(index + 1), ...ordered.slice(0, Math.max(0, index))];
    const next = after.find((candidate) => !candidate.annotation && !saved[candidate.id]?.annotation);
    if (next) select(next);
  }

  function moveBound(which: "start" | "end", seconds: number) {
    const value = Math.min(duration, Math.max(0, Math.round(seconds * 1000) / 1000));
    editDraft(which === "start" ? { startText: String(value) } : { endText: String(value) });
  }

  async function decide(verdict: "true_positive" | "false_positive") {
    if (!selected || readOnly || savingId !== null) return;
    const interval = reviewInterval(startText, endText, duration);
    if ("error" in interval) {
      setInputError(interval.error);
      return;
    }
    const adjusted = interval.start !== selected.start_seconds || interval.end !== selected.end_seconds;
    setSavingId(selected.id);
    setSaveError(null);
    try {
      const result = await api.upsertAnnotation(selected.id, {
        verdict,
        ...(adjusted ? { corrected_start_seconds: interval.start, corrected_end_seconds: interval.end } : {}),
        note: note.trim(),
        reviewer,
      });
      if (drafts.get(draftKey(selected.id)) === draft) drafts.delete(draftKey(selected.id));
      const merged = withAnnotation(selected, result.annotation);
      setSaved((current) => ({ ...current, [selected.id]: merged }));
      setLive(`Candidate ${verdict === "true_positive" ? "accepted" : "rejected"}.`);
      if (autoAdvance) {
        const index = ordered.findIndex((candidate) => candidate.id === selected.id);
        const after = [...ordered.slice(index + 1), ...ordered.slice(0, index)];
        const next = after.find((candidate) => candidate.id !== selected.id && !(saved[candidate.id] ?? candidate).annotation);
        if (next) setSelectedId((current) => current === selected.id ? next.id : current);
      }
    } catch (failure) {
      setSaveError({ id: selected.id, error: toApiError(failure) });
    } finally {
      setSavingId(null);
    }
  }

  function togglePlay() {
    const element = videoRef.current;
    if (!element) return;
    if (element.paused) void element.play().catch(() => undefined);
    else element.pause();
  }

  keyHandler.current = (event: KeyboardEvent) => {
    if (showShortcuts || isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
    const key = event.key;
    if (key === "a" || key === "A" || key === "j" || key === "J") {
      event.preventDefault();
      void decide("true_positive");
    } else if (key === "r" || key === "R" || key === "f" || key === "F") {
      event.preventDefault();
      void decide("false_positive");
    } else if (key === "n" || key === "N") {
      event.preventDefault();
      nextUnreviewed();
    } else if (key === "ArrowDown") {
      event.preventDefault();
      step(1);
    } else if (key === "ArrowUp") {
      event.preventDefault();
      step(-1);
    } else if (key === " ") {
      event.preventDefault();
      togglePlay();
    } else if (key === "?") {
      event.preventDefault();
      setShowShortcuts(true);
    }
  };

  useEffect(() => {
    const listener = (event: KeyboardEvent) => keyHandler.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  // --- zoomed adjustment track --------------------------------------------- //
  const span = selected ? Math.max(selected.end_seconds - selected.start_seconds, 1) : 1;
  const pad = Math.max(5, span);
  const windowStart = selected ? Math.max(0, Math.min(selected.start_seconds, startValue) - pad) : 0;
  const windowEnd = selected
    ? Math.min(duration || selected.end_seconds + pad, Math.max(selected.end_seconds, endValue) + pad)
    : 1;
  const windowLength = Math.max(windowEnd - windowStart, 0.1);
  const toPct = (time: number) => percent((time - windowStart) / windowLength, 2);

  function timeFromPointer(clientX: number): number {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return windowStart;
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return windowStart + ratio * windowLength;
  }

  function onHandleDown(which: "start" | "end", event: ReactPointerEvent<HTMLSpanElement>) {
    if (editingDisabled) return;
    event.preventDefault();
    event.stopPropagation();
    dragging.current = which;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onHandleMove(event: ReactPointerEvent<HTMLSpanElement>) {
    if (!dragging.current) return;
    const time = timeFromPointer(event.clientX);
    if (dragging.current === "start") moveBound("start", Math.min(time, endValue - 0.1));
    else moveBound("end", Math.max(time, startValue + 0.1));
  }

  function onHandleUp() {
    dragging.current = null;
  }

  function onTrackClick(event: ReactMouseEvent<HTMLDivElement>) {
    const element = videoRef.current;
    if (!element || view !== "full") return;
    element.currentTime = timeFromPointer(event.clientX);
  }

  // ------------------------------------------------------------------------ //

  if (data.loading && !data.data) {
    return (
      <div className="page">
        <Loading label="Loading candidates…" />
      </div>
    );
  }
  if (!data.data || !data.data.action) {
    return (
      <div className="page">
        {data.error ? (
          <ErrorNotice error={data.error} onRetry={data.reload} />
        ) : (
          <Notice tone="warning">This search does not exist anymore.</Notice>
        )}
      </div>
    );
  }

  const { project, action, adapters } = data.data;
  const reviewed = counts.accepted + counts.rejected;
  const sameVideo = selected ? candidates.filter((candidate) => candidate.video_id === selected.video_id) : [];
  const adjusted =
    selected &&
    (startValue !== selected.start_seconds || endValue !== selected.end_seconds);
  const position = selected ? visible.findIndex((candidate) => candidate.id === selected.id) + 1 : 0;

  return (
    <div className="review">
      <AriaLive message={live} />
      <header className="review__header">
        <div className="review__title">
          <div className="crumbs small">
            <a href={`#/datasets/${datasetId}`}>{project.name}</a>
            <span>/</span>
            <a href={`#/datasets/${datasetId}/searches/${searchId}`}>{action.name}</a>
          </div>
          <div className="review__prompt">
            <span className="muted">Is this: </span>“{action.description}”
          </div>
        </div>
        <div className="review__progress">
          <div className="row-between small tabular">
            <strong>
              {reviewed} of {counts.all} reviewed
            </strong>
            <span className="muted">
              {counts.accepted} accepted · {counts.rejected} rejected
            </span>
          </div>
          <div className="split-bar" aria-hidden="true">
            <span className="split-bar__ok" style={{ width: percent(counts.all ? counts.accepted / counts.all : 0, 2) }} />
            <span className="split-bar__bad" style={{ width: percent(counts.all ? counts.rejected / counts.all : 0, 2) }} />
          </div>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-icon"
          aria-label="Keyboard shortcuts"
          title="Keyboard shortcuts (?)"
          onClick={() => setShowShortcuts(true)}
        >
          <Icon name="keyboard" size={17} />
        </button>
      </header>

      {adapters.includes("mock") ? (
        <div className="banner-mock" role="status">
          <strong>Mock candidates.</strong> This search used the mock model: no video pixels were analysed, so
          timestamps and scores are placeholders.
        </div>
      ) : null}

      <div className="review__body">
        <aside className="review__list" aria-label="Candidates">
          <div className="review__filters">
            <div className="seg-filter" role="tablist" aria-label="Filter by review status">
              {FILTERS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  role="tab"
                  aria-selected={filter === item.value}
                  className={filter === item.value ? "seg-filter__opt is-on" : "seg-filter__opt"}
                  onClick={() => setFilter(item.value)}
                >
                  <span>{item.label}</span>
                  <span className="tabular strong">{counts[item.value]}</span>
                </button>
              ))}
            </div>
            <div className="row-between small muted">
              <span className="tabular">
                {visible.length} {visible.length === 1 ? "candidate" : "candidates"} · {videoCount}{" "}
                {videoCount === 1 ? "video" : "videos"}
              </span>
              <span className="row">
                Sort
                {(["confidence", "time"] as Sort[]).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={sort === value ? "sort-opt is-on" : "sort-opt"}
                    onClick={() => setSort(value)}
                  >
                    {value === "confidence" ? "Confidence" : "Time"}
                  </button>
                ))}
              </span>
            </div>
          </div>

          <ol className="cand-list">
            {visible.map((candidate) => {
              const bounds = finalBounds(candidate);
              const video = videoById.get(candidate.video_id);
              const status = reviewStatus(candidate);
              const ownerName = videoReviewer(candidates, candidate.video_id);
              const lock = Boolean(session.user && ownerName && ownerName !== reviewer);
              return (
                <li key={candidate.id}>
                  <button
                    type="button"
                    className={candidate.id === selectedId ? "cand is-current" : "cand"}
                    aria-current={candidate.id === selectedId ? "true" : undefined}
                    onClick={() => select(candidate)}
                  >
                    <span className="cand__thumb" aria-hidden="true">
                      {formatClock(bounds.start)}
                    </span>
                    <span className="cand__body">
                      <span className="cand__line">
                        <span className="truncate">{video?.original_filename ?? `Video ${candidate.video_id}`}</span>
                        <span className="tabular muted">
                          {formatClock(bounds.start)}–{formatClock(bounds.end)}
                        </span>
                      </span>
                      <span className="cand__line">
                        <span className="conf" title="Model confidence (not calibrated)">
                          <span className="conf__bar">
                            <span style={{ width: percent(Math.min(1, Math.max(0, candidate.score))) }} />
                          </span>
                          {formatScore(candidate.score)}
                          {candidate.annotation?.corrected_start_seconds != null ? " · adjusted" : ""}
                        </span>
                        <span className="row">
                          {lock ? <Icon name="lock" size={12} className="muted" /> : null}
                          <ReviewChip status={status} />
                        </span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
          {visible.length === 0 && candidates.length > 0 ? (
            <div className="review__empty-filter">
              <span>No candidates match this filter.</span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setFilter("all")}>
                Show all
              </button>
            </div>
          ) : null}
        </aside>

        <section className="review__detail" aria-label="Selected candidate">
          {candidates.length === 0 ? (
            <div className="page">
              <EmptyState title="No candidates to review">This search didn’t return any clips.</EmptyState>
            </div>
          ) : null}

          {counts.unreviewed === 0 && candidates.length > 0 ? (
            <Notice tone="ok" title="All candidates reviewed">
              {counts.accepted} accepted, {counts.rejected} rejected. Decisions are final.{" "}
              {session.canManage ? <a href={`#/export?dataset=${datasetId}`}>Export the dataset</a> : null}
            </Notice>
          ) : null}

          {selected && selectedVideo ? (
            <>
              <div className="player">
                <div className="player__bar">
                  <span className="small">
                    {selectedVideo.original_filename} · {view === "full" ? "full video" : "clip"}
                  </span>
                  <div className="seg-mini" role="group" aria-label="Player view">
                    <button
                      type="button"
                      className={view === "full" ? "is-on" : ""}
                      onClick={() => setView("full")}
                    >
                      Full video
                    </button>
                    <button
                      type="button"
                      className={view === "clip" ? "is-on" : ""}
                      disabled={selected.clip_status !== "ready"}
                      title={selected.clip_status !== "ready" ? `Clip ${selected.clip_status}` : undefined}
                      onClick={() => setView("clip")}
                    >
                      Clip
                    </button>
                  </div>
                </div>
                <video
                  key={view === "full" ? `v-${selected.video_id}` : `c-${selected.id}`}
                  ref={videoRef}
                  className="player__video"
                  src={view === "full" ? videoStreamUrl(selected.video_id) : candidateClipUrl(selected.id)}
                  controls
                  preload="metadata"
                  loop={view === "clip"}
                  onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                  onSeeked={(event) => setCurrentTime(event.currentTarget.currentTime)}
                  onPlay={() => setPaused(false)}
                  onPause={() => setPaused(true)}
                />
              </div>

              <div className="player__meta small">
                <button type="button" className="btn btn-secondary btn-icon btn-sm" onClick={togglePlay} aria-label={paused ? "Play" : "Pause"}>
                  <Icon name={paused ? "play" : "pause"} size={14} />
                </button>
                <span className="tabular">{formatTimestamp(view === "full" ? currentTime : selected.preview_start_seconds + currentTime)}</span>
                <span className="muted">Space to play / pause</span>
                <span className="push-right muted">
                  Confidence <strong className="tabular">{formatScore(selected.score)}</strong>
                </span>
              </div>

              <div className="timeline">
                <div className="row-between small muted">
                  <span>{selectedVideo.original_filename} · full video</span>
                  <span className="tabular">{formatClock(duration)}</span>
                </div>
                <div className="timeline__full" aria-hidden="true">
                  {sameVideo.map((candidate) => {
                    const bounds = finalBounds(candidate);
                    return (
                      <span
                        key={candidate.id}
                        className={candidate.id === selected.id ? "tl-block is-current" : `tl-block tl-block--${reviewStatus(candidate)}`}
                        style={{
                          left: percent(duration ? bounds.start / duration : 0, 2),
                          width: percent(duration ? Math.max(bounds.end - bounds.start, 0.2) / duration : 0, 2),
                        }}
                      />
                    );
                  })}
                  {view === "full" && duration ? (
                    <span className="tl-head" style={{ left: percent(currentTime / duration, 2) }} />
                  ) : null}
                </div>

                <div className="row-between small muted">
                  <span>{readOnly ? "Start and end" : "Adjust start and end — drag the handles"}</span>
                  {adjusted ? (
                    <span className="row">
                      Adjusted from {formatClock(selected.start_seconds)}–{formatClock(selected.end_seconds)}
                      {!readOnly ? (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={editingDisabled}
                          onClick={() => editDraft({ startText: String(selected.start_seconds), endText: String(selected.end_seconds) })}
                        >
                          Reset
                        </button>
                      ) : null}
                    </span>
                  ) : null}
                </div>
                <div
                  ref={trackRef}
                  className={readOnly ? "track is-readonly" : "track"}
                  onClick={onTrackClick}
                  role="presentation"
                >
                  <span
                    className="track__orig"
                    style={{ left: toPct(selected.start_seconds), width: percent((selected.end_seconds - selected.start_seconds) / windowLength, 2) }}
                  />
                  <span
                    className="track__sel"
                    style={{ left: toPct(startValue), width: percent(Math.max(endValue - startValue, 0) / windowLength, 2) }}
                  />
                  {view === "full" && currentTime >= windowStart && currentTime <= windowEnd ? (
                    <span className="track__head" style={{ left: toPct(currentTime) }} />
                  ) : null}
                  {(["start", "end"] as const).map((which) => (
                    <span
                      key={which}
                      role="slider"
                      tabIndex={editingDisabled ? -1 : 0}
                      aria-label={which === "start" ? "Event start" : "Event end"}
                      aria-valuemin={0}
                      aria-valuemax={duration}
                      aria-valuenow={which === "start" ? startValue : endValue}
                      aria-valuetext={formatTimestamp(which === "start" ? startValue : endValue)}
                      aria-disabled={editingDisabled}
                      className={`track__handle track__handle--${which}`}
                      style={{ left: toPct(which === "start" ? startValue : endValue) }}
                      onPointerDown={(event) => onHandleDown(which, event)}
                      onPointerMove={onHandleMove}
                      onPointerUp={onHandleUp}
                      onClick={(event) => event.stopPropagation()}
                      onKeyDown={(event) => {
                        if (editingDisabled) return;
                        const delta = event.key === "ArrowLeft" ? -0.1 : event.key === "ArrowRight" ? 0.1 : 0;
                        if (!delta) return;
                        event.preventDefault();
                        event.stopPropagation();
                        if (which === "start") moveBound("start", startValue + delta);
                        else moveBound("end", endValue + delta);
                      }}
                    />
                  ))}
                </div>
                <div className="row-between small muted tabular">
                  <span>{formatClock(windowStart)}</span>
                  <span>{formatClock((windowStart + windowEnd) / 2)}</span>
                  <span>{formatClock(windowEnd)}</span>
                </div>

                <div className="bounds">
                  {(["start", "end"] as const).map((which) => (
                    <div className="field" key={which}>
                      <label htmlFor={`bound-${which}`}>{which === "start" ? "Start (s)" : "End (s)"}</label>
                      <div className="stepper">
                        <button
                          type="button"
                          className="btn btn-secondary btn-icon"
                          disabled={editingDisabled}
                          aria-label={`${which} minus half a second`}
                          onClick={() =>
                            moveBound(which, (which === "start" ? startValue : endValue) - STEP)
                          }
                        >
                          −
                        </button>
                        <input
                          id={`bound-${which}`}
                          className="input tabular"
                          inputMode="decimal"
                          disabled={editingDisabled}
                          value={which === "start" ? startText : endText}
                          onChange={(event) => {
                            const value = event.target.value;
                            editDraft(which === "start" ? { startText: value } : { endText: value });
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") (event.target as HTMLInputElement).blur();
                          }}
                        />
                        <button
                          type="button"
                          className="btn btn-secondary btn-icon"
                          disabled={editingDisabled}
                          aria-label={`${which} plus half a second`}
                          onClick={() =>
                            moveBound(which, (which === "start" ? startValue : endValue) + STEP)
                          }
                        >
                          +
                        </button>
                      </div>
                    </div>
                  ))}
                  <div className="bounds__len muted small tabular">
                    {formatClock(startValue)}–{formatClock(endValue)} · length {Math.max(endValue - startValue, 0).toFixed(1)} s
                  </div>
                </div>
                {inputError ? <div role="alert" className="field-error">{inputError}</div> : null}
              </div>

              {lockedByOther && !decided ? (
                <Notice tone="warning" title="Reviewed by someone else">
                  {owner} reviews this video (one reviewer per video). Its candidates are read-only for you.
                </Notice>
              ) : null}

              {decided && selected.annotation ? (
                <Notice tone={selected.annotation.verdict === "true_positive" ? "ok" : "danger"} title={`${reviewStatus(selected) === "accepted" ? "Accepted" : "Rejected"} — decision is final`}>
                  By {selected.annotation.reviewer || "anonymous"}
                  {selected.annotation.note ? ` · “${selected.annotation.note}”` : ""}
                </Notice>
              ) : null}

              {!readOnly ? (
                <div className="decide">
                  <button
                    type="button"
                    className="decide__btn decide__btn--reject blueprint"
                    disabled={savingId !== null}
                    onClick={() => void decide("false_positive")}
                    aria-label="Reject candidate (R)"
                  >
                    <Icon name="cross" size={18} />
                    Reject
                    <kbd>R</kbd>
                  </button>
                  <button
                    type="button"
                    className="decide__btn decide__btn--accept blueprint"
                    disabled={savingId !== null}
                    onClick={() => void decide("true_positive")}
                    aria-label="Accept candidate (A)"
                  >
                    <Icon name="check" size={18} />
                    Accept
                    <kbd>A</kbd>
                  </button>
                </div>
              ) : null}
              {saveError?.id === selected.id ? <ErrorNotice error={saveError.error} title="The decision was not saved" /> : null}

              <div className="review__nav">
                <button type="button" className="btn btn-secondary" onClick={() => step(-1)}>
                  ↑ Previous
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => step(1)}>
                  ↓ Next
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => nextUnreviewed()}>
                  Next unreviewed <kbd>N</kbd>
                </button>
                <label className="check small">
                  <input
                    type="checkbox"
                    checked={autoAdvance}
                    onChange={(event) => setAutoAdvance(event.target.checked)}
                  />
                  Go to the next unreviewed after a decision
                </label>
                <span className="push-right muted small tabular">
                  {position} of {visible.length}
                </span>
              </div>

              <div className="review__extra">
                <div className="field">
                  <label htmlFor="review-note">Note</label>
                  <textarea
                    id="review-note"
                    className="input"
                    value={note}
                    disabled={editingDisabled}
                    maxLength={2000}
                    onChange={(event) => {
                      const value = event.target.value;
                      editDraft({ note: value });
                    }}
                    placeholder="Optional — e.g. forklift partly hidden by a shelf"
                  />
                  {!session.user ? (
                    <>
                      <label htmlFor="review-reviewer" className="spaced">
                        Reviewer name <span className="muted">(development mode, no account)</span>
                      </label>
                      <input
                        id="review-reviewer"
                        className="input"
                        value={openReviewer}
                        maxLength={100}
                        onChange={(event) => setOpenReviewer(event.target.value)}
                        placeholder="anonymous"
                      />
                    </>
                  ) : null}
                </div>
                <dl className="facts">
                  <dt>Video</dt>
                  <dd>{selectedVideo.original_filename}</dd>
                  <dt>Model times</dt>
                  <dd className="tabular">
                    {formatTimestamp(selected.start_seconds)} – {formatTimestamp(selected.end_seconds)}
                  </dd>
                  <dt>Status</dt>
                  <dd>{reviewStatus(selected)}</dd>
                  <dt>Candidate</dt>
                  <dd className="tabular">#{selected.id}</dd>
                  {selected.model_notes ? (
                    <>
                      <dt>Model notes</dt>
                      <dd>{selected.model_notes}</dd>
                    </>
                  ) : null}
                </dl>
              </div>
            </>
          ) : null}
        </section>
      </div>

      {showShortcuts ? (
        <Dialog
          title="Keyboard shortcuts"
          onClose={() => setShowShortcuts(false)}
          actions={
            <button type="button" className="btn btn-secondary" onClick={() => setShowShortcuts(false)}>
              Close
            </button>
          }
        >
          <div className="shortcuts">
            {SHORTCUTS.map(([key, label]) => (
              <div key={key} className="shortcuts__row">
                <kbd>{key}</kbd>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}
