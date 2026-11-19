import { describe, expect, it } from "vitest";

import type { Annotation, Candidate, Job, Project, Video } from "../types";
import {
  buildExportDocument,
  countReview,
  finalBounds,
  promptTitle,
  summarizeSearch,
  uniqueName,
  unprocessedVideos,
  videoReviewer,
} from "./search";

function job(overrides: Partial<Job>): Job {
  return {
    id: 1,
    kind: "candidate_proposal",
    status: "queued",
    project_id: 1,
    video_id: 1,
    action_id: 1,
    export_id: null,
    progress: 0,
    attempts: 0,
    max_attempts: 3,
    adapter_name: "mock",
    adapter_version: "1.0.0",
    error_code: null,
    error_message: null,
    available_at: "2026-11-19T10:00:00Z",
    created_at: "2026-11-19T10:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

function annotation(overrides: Partial<Annotation>): Annotation {
  return {
    verdict: "true_positive",
    corrected_start_seconds: null,
    corrected_end_seconds: null,
    note: "",
    reviewer: "ana@example.com",
    created_at: "2026-11-19T10:00:00Z",
    updated_at: "2026-11-19T10:00:00Z",
    ...overrides,
  };
}

function candidate(overrides: Partial<Candidate>): Candidate {
  return {
    id: 1,
    job_id: 1,
    video_id: 1,
    action_id: 1,
    start_seconds: 10,
    end_seconds: 15,
    preview_start_seconds: 9,
    preview_end_seconds: 16,
    rank: 1,
    score: 0.9,
    model_notes: "",
    clip_status: "ready",
    clip_error: null,
    review_state: "unreviewed",
    annotation: null,
    ...overrides,
  };
}

describe("summarizeSearch", () => {
  it("reports empty, queued, running, done, partial and failed", () => {
    expect(summarizeSearch([]).status).toBe("empty");
    expect(summarizeSearch([job({ id: 1 }), job({ id: 2, video_id: 2 })]).status).toBe("queued");
    expect(
      summarizeSearch([job({ id: 1, status: "running", progress: 0.5 }), job({ id: 2, video_id: 2 })])
        .status,
    ).toBe("running");
    expect(
      summarizeSearch([job({ id: 1, status: "succeeded" }), job({ id: 2, video_id: 2 })]).status,
    ).toBe("running");
    expect(
      summarizeSearch([
        job({ id: 1, status: "succeeded" }),
        job({ id: 2, video_id: 2, status: "succeeded" }),
      ]).status,
    ).toBe("done");
    expect(
      summarizeSearch([job({ id: 1, status: "succeeded" }), job({ id: 2, video_id: 2, status: "failed" })])
        .status,
    ).toBe("partial");
    expect(summarizeSearch([job({ id: 1, status: "failed" })]).status).toBe("failed");
  });

  it("keeps only the latest job per video and averages progress", () => {
    const summary = summarizeSearch([
      job({ id: 1, status: "failed" }),
      job({ id: 5, status: "running", progress: 0.5 }),
      job({ id: 2, video_id: 2, status: "succeeded" }),
    ]);
    expect(summary.videosTotal).toBe(2);
    expect(summary.status).toBe("running");
    expect(summary.progress).toBeCloseTo(0.75);
  });

  it("ignores export jobs", () => {
    expect(summarizeSearch([job({ kind: "dataset_export", video_id: null })]).status).toBe("empty");
  });
});

describe("unprocessedVideos", () => {
  const video = (id: number, status: Video["status"] = "ready") => ({ id, status }) as Video;

  it("lists ready videos without a job, or with only a canceled one", () => {
    const videos = [video(1), video(2), video(3), video(4), video(5, "failed")];
    const jobs = [
      job({ id: 1, video_id: 1, status: "succeeded" }),
      job({ id: 2, video_id: 2, status: "canceled" }),
      job({ id: 3, video_id: 4, status: "failed" }),
    ];
    expect(unprocessedVideos(videos, jobs).map((item) => item.id)).toEqual([2, 3]);
  });

  it("uses the latest job of each video", () => {
    const jobs = [job({ id: 1, video_id: 1, status: "canceled" }), job({ id: 2, video_id: 1, status: "queued" })];
    expect(unprocessedVideos([video(1)], jobs)).toEqual([]);
  });
});

describe("review helpers", () => {
  it("counts review states", () => {
    expect(
      countReview([
        candidate({ id: 1 }),
        candidate({ id: 2, annotation: annotation({}) }),
        candidate({ id: 3, annotation: annotation({ verdict: "false_positive" }) }),
      ]),
    ).toEqual({ all: 3, unreviewed: 1, accepted: 1, rejected: 1 });
  });

  it("uses corrected bounds when present", () => {
    expect(finalBounds(candidate({}))).toEqual({ start: 10, end: 15 });
    expect(
      finalBounds(
        candidate({ annotation: annotation({ corrected_start_seconds: 11, corrected_end_seconds: 14 }) }),
      ),
    ).toEqual({ start: 11, end: 14 });
  });

  it("finds the first reviewer of a video (REV-5)", () => {
    const list = [
      candidate({ id: 1, annotation: annotation({ reviewer: "late", created_at: "2026-11-19T12:00:00Z" }) }),
      candidate({ id: 2, annotation: annotation({ reviewer: "first", created_at: "2026-11-19T09:00:00Z" }) }),
      candidate({ id: 3, video_id: 2, annotation: annotation({ reviewer: "other" }) }),
    ];
    expect(videoReviewer(list, 1)).toBe("first");
    expect(videoReviewer(list, 3)).toBeNull();
  });
});

describe("names", () => {
  it("builds a short title from a long prompt (PR-3)", () => {
    expect(promptTitle("A forklift enters the zone marked by orange lines on the floor.")).toBe(
      "A forklift enters the zone marked by orange…",
    );
    expect(promptTitle("A person is putting on a helmet.")).toBe("A person is putting on a helmet");
    expect(promptTitle("A worker walks into the loading area of the warehouse at night")).toBe(
      "A worker walks into the loading area…",
    );
    expect(promptTitle("person waves.")).toBe("Person waves");
    expect(promptTitle("   ")).toBe("Untitled search");
  });

  it("makes action names unique", () => {
    expect(uniqueName("Door", [])).toBe("Door");
    expect(uniqueName("Door", ["door", "Door (2)"])).toBe("Door (3)");
  });
});

describe("buildExportDocument", () => {
  const project: Project = {
    id: 1,
    name: "Warehouse",
    description: "",
    created_at: "2026-11-19T10:00:00Z",
    updated_at: "2026-11-19T10:00:00Z",
  };
  const videos = [{ id: 1, original_filename: "cam01.mp4" } as Video];
  const action = {
    id: 1,
    project_id: 1,
    name: "Door",
    description: "Person opens a door",
    created_at: "",
    updated_at: "",
  };
  const candidates = [
    candidate({ id: 1, annotation: annotation({ corrected_start_seconds: 11, corrected_end_seconds: 14 }) }),
    candidate({ id: 2, annotation: annotation({ verdict: "false_positive" }) }),
    candidate({ id: 3 }),
  ];

  it("exports accepted annotations only by default", () => {
    const doc = buildExportDocument(project, [{ action, candidates, adapters: ["mock"] }], videos, false);
    expect(doc.dataset).toBe("Warehouse");
    expect(doc.searches[0].prompt).toBe("Person opens a door");
    expect(doc.searches[0].annotations).toHaveLength(1);
    expect(doc.searches[0].annotations[0]).toMatchObject({
      video: "cam01.mp4",
      start_s: 11,
      end_s: 14,
      status: "accepted",
      original_start_s: 10,
    });
  });

  it("adds rejected candidates when asked and never exports unreviewed ones", () => {
    const doc = buildExportDocument(project, [{ action, candidates, adapters: [] }], videos, true);
    expect(doc.searches[0].annotations.map((item) => item.status)).toEqual(["accepted", "rejected"]);
  });
});
