/**
 * Pure helpers that map the current backend onto the v1.2 concepts.
 *
 * The backend has no Search entity yet: a "search" in the interface is one
 * ActionDefinition (the prompt) plus one candidate job per video of the dataset
 * (`POST /projects/{id}/actions/{action_id}/jobs`). These helpers aggregate the
 * jobs into the four search states of the Design Description (4.4) and build the
 * client-side JSON export (Design 4.3 proposal, EXP-1).
 */
import type { ActionDefinition, Candidate, Job, Project, UserRole, Video } from "../types";

export type SearchStatus = "queued" | "running" | "done" | "partial" | "failed" | "empty";
export type ReviewStatus = "unreviewed" | "accepted" | "rejected";

export interface SearchSummary {
  status: SearchStatus;
  /** 0..1 over all video jobs of the search. */
  progress: number;
  jobs: Job[];
  videosTotal: number;
  videosDone: number;
  videosFailed: number;
  adapters: string[];
  /** Latest job per video: re-runs and retries replace older attempts. */
  latestByVideo: Map<number, Job>;
}

/** Keeps the newest candidate-proposal job per video. */
export function latestJobsByVideo(jobs: Job[]): Map<number, Job> {
  const latest = new Map<number, Job>();
  for (const job of jobs) {
    if (job.kind !== "candidate_proposal" || job.video_id === null) {
      continue;
    }
    const current = latest.get(job.video_id);
    if (!current || job.id > current.id) {
      latest.set(job.video_id, job);
    }
  }
  return latest;
}

/** Aggregates the video jobs of one search into a single status (Design 4.4). */
export function summarizeSearch(jobs: Job[]): SearchSummary {
  const latestByVideo = latestJobsByVideo(jobs);
  const latest = [...latestByVideo.values()];
  const total = latest.length;
  const done = latest.filter((job) => job.status === "succeeded").length;
  const failed = latest.filter((job) => job.status === "failed" || job.status === "canceled").length;
  const running = latest.some((job) => job.status === "running");
  const queued = latest.some((job) => job.status === "queued");

  let status: SearchStatus;
  if (total === 0) {
    status = "empty";
  } else if (running || (queued && done + failed > 0)) {
    status = "running";
  } else if (queued) {
    status = "queued";
  } else if (failed === total) {
    status = "failed";
  } else if (failed > 0) {
    status = "partial";
  } else {
    status = "done";
  }

  const progress =
    total === 0
      ? 0
      : latest.reduce((sum, job) => sum + (job.status === "succeeded" ? 1 : job.progress), 0) /
        total;
  const adapters = [...new Set(latest.map((job) => job.adapter_name).filter(Boolean))] as string[];

  return {
    status,
    progress: Math.min(1, Math.max(0, progress)),
    jobs: latest,
    videosTotal: total,
    videosDone: done,
    videosFailed: failed,
    adapters,
    latestByVideo,
  };
}

export function isActive(status: SearchStatus): boolean {
  return status === "queued" || status === "running";
}

export function reviewStatus(candidate: Candidate): ReviewStatus {
  if (!candidate.annotation) {
    return "unreviewed";
  }
  return candidate.annotation.verdict === "true_positive" ? "accepted" : "rejected";
}

export interface ReviewCounts {
  all: number;
  unreviewed: number;
  accepted: number;
  rejected: number;
}

export function countReview(candidates: Candidate[]): ReviewCounts {
  const counts: ReviewCounts = { all: candidates.length, unreviewed: 0, accepted: 0, rejected: 0 };
  for (const candidate of candidates) {
    counts[reviewStatus(candidate)] += 1;
  }
  return counts;
}

const TRAILING_STOPWORDS = new Set([
  "a", "an", "the", "of", "on", "in", "at", "to", "by", "and", "or", "with", "from", "for", "into", "is", "are",
]);

/**
 * Short automatic title for a long prompt (PR-3, "Could"): the prompt itself
 * when it is short, otherwise its first words, never ending on a small word.
 */
export function promptTitle(prompt: string, maxWords = 8, maxChars = 56): string {
  const clean = prompt.replace(/\s+/g, " ").trim().replace(/[.!?;:,]+$/, "");
  if (!clean) {
    return "Untitled search";
  }
  const words = clean.split(" ");
  let kept = words.slice(0, maxWords);
  while (kept.join(" ").length > maxChars && kept.length > 1) {
    kept = kept.slice(0, -1);
  }
  const truncated = kept.length < words.length;
  while (truncated && kept.length > 1 && TRAILING_STOPWORDS.has(kept[kept.length - 1].toLowerCase())) {
    kept = kept.slice(0, -1);
  }
  let title = kept.join(" ");
  if (title.length > maxChars) {
    title = title.slice(0, maxChars - 1).trimEnd();
  }
  if (truncated) {
    title = `${title}…`;
  }
  return title.charAt(0).toUpperCase() + title.slice(1);
}

/** Action names are unique per project; suffix " (2)", " (3)"… when needed. */
export function uniqueName(base: string, taken: Iterable<string>): string {
  const used = new Set([...taken].map((name) => name.toLowerCase()));
  const trimmed = base.trim().slice(0, 190) || "Search";
  if (!used.has(trimmed.toLowerCase())) {
    return trimmed;
  }
  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${trimmed} (${index})`;
    if (!used.has(candidate.toLowerCase())) {
      return candidate;
    }
  }
  return `${trimmed} (${Date.now()})`;
}

/** Final timestamps: the reviewer's correction when present, otherwise the proposal. */
export function finalBounds(candidate: Candidate): { start: number; end: number } {
  const annotation = candidate.annotation;
  if (
    annotation &&
    annotation.corrected_start_seconds !== null &&
    annotation.corrected_end_seconds !== null
  ) {
    return { start: annotation.corrected_start_seconds, end: annotation.corrected_end_seconds };
  }
  return { start: candidate.start_seconds, end: candidate.end_seconds };
}

/**
 * REV-5 (one reviewer per video). The backend does not lock videos yet, so the
 * client derives the owner from the first saved decision on that video.
 */
export function videoReviewer(candidates: Candidate[], videoId: number): string | null {
  let first: { at: string; reviewer: string } | null = null;
  for (const candidate of candidates) {
    if (candidate.video_id !== videoId || !candidate.annotation) {
      continue;
    }
    const at = candidate.annotation.created_at;
    if (!first || at < first.at) {
      first = { at, reviewer: candidate.annotation.reviewer };
    }
  }
  return first?.reviewer ?? null;
}

export function canManage(role: UserRole): boolean {
  return role === "administrator" || role === "dataset_admin";
}

export const ROLE_LABEL: Record<UserRole, string> = {
  administrator: "Administrator",
  dataset_admin: "Dataset Administrator",
  annotator: "Annotator",
};

export interface ExportSearch {
  action: ActionDefinition;
  candidates: Candidate[];
  adapters: string[];
}

/**
 * JSON export built in the browser from reviewed candidates (EXP-1, EXP-2).
 * Structure: the first proposal of Design Description 4.3; the OpenLABEL-based
 * schema is still being agreed with the customer. Unreviewed candidates are never
 * exported; rejected ones only when `includeRejected` is set (EXP-2).
 */
export function buildExportDocument(
  project: Project,
  searches: ExportSearch[],
  videos: Video[],
  includeRejected: boolean,
  exportedAt: Date = new Date(),
) {
  const videoById = new Map(videos.map((video) => [video.id, video]));
  return {
    format: "vlm-annotate/annotations",
    format_version: "0.1",
    format_note:
      "First proposal (Design Description v1.2, 4.3). To be replaced by the OpenLABEL-based structure.",
    dataset: project.name,
    exported_at: exportedAt.toISOString(),
    include_rejected: includeRejected,
    searches: searches.map(({ action, candidates, adapters }) => ({
      prompt: action.description,
      title: action.name,
      model: adapters.join(", ") || null,
      annotations: candidates
        .filter((candidate) => {
          const status = reviewStatus(candidate);
          return status === "accepted" || (includeRejected && status === "rejected");
        })
        .map((candidate) => {
          const bounds = finalBounds(candidate);
          const video = videoById.get(candidate.video_id);
          return {
            video: video?.original_filename ?? `video-${candidate.video_id}`,
            start_s: bounds.start,
            end_s: bounds.end,
            status: reviewStatus(candidate),
            original_start_s: candidate.start_seconds,
            original_end_s: candidate.end_seconds,
            confidence: candidate.score,
            reviewer: candidate.annotation?.reviewer ?? null,
            reviewed_at: candidate.annotation?.updated_at ?? null,
          };
        }),
    })),
  };
}
