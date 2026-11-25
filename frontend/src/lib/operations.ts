/**
 * Multi-call operations on a dataset that the current API does not offer as a
 * single endpoint.
 */
import type { ActionDefinition, ActionInput, Video } from "../types";
import { api, ApiError, newIdempotencyKey } from "./api";
import { summarizeSearch, unprocessedVideos } from "./search";

export async function prepareSearch(projectId: number, input: ActionInput, adapter: string) {
  const action = await api.createAction(projectId, input);
  const key = newIdempotencyKey();
  return {
    action,
    async enqueue() {
      // An error can mean the server committed the jobs and the response was lost.
      const jobs = await api.createActionJobs(projectId, action.id, { adapter }, key);
      if (jobs.length === 0) {
        throw new ApiError(0, "NO_READY_VIDEOS", "No ready videos were available. Check the dataset and try again.");
      }
    },
  };
}

/**
 * Deletes a search (prompt). Queued and running jobs are canceled first, then
 * `DELETE /actions/{id}` removes the action with its jobs, candidates, review
 * decisions, clips and engine work directories.
 */
export async function deleteSearch(projectId: number, actionId: number): Promise<void> {
  const jobs = await api.listJobs({ projectId, actionId, limit: 200 });
  for (const job of jobs) {
    if (job.status === "queued" || job.status === "running") {
      try {
        await api.cancelJob(job.id);
      } catch {
        // The job finished in the meantime: nothing left to cancel.
      }
    }
  }
  await api.deleteAction(actionId);
}

export interface PendingSearch {
  action: ActionDefinition;
  videos: Video[];
  adapter: string | undefined;
}

/** Fresh list of (search, unprocessed videos) pairs, read from the API (DS-7). */
export async function findPendingSearches(
  projectId: number,
  actions: ActionDefinition[],
  videos: Video[],
): Promise<PendingSearch[]> {
  const pending: PendingSearch[] = [];
  for (const action of actions) {
    const jobs = await api.listJobs({ projectId, actionId: action.id, limit: 200 });
    const missing = unprocessedVideos(videos, jobs);
    if (missing.length > 0) {
      // Keep the model the search already used; fall back to the default model.
      pending.push({ action, videos: missing, adapter: summarizeSearch(jobs).adapters[0] });
    }
  }
  return pending;
}

/** Queues one job per (search, unprocessed video). Returns the number of jobs queued. */
export async function runPendingSearches(projectId: number, pending: PendingSearch[]): Promise<number> {
  let queued = 0;
  for (const item of pending) {
    const jobs = await api.createActionJobs(
      projectId,
      item.action.id,
      { video_ids: item.videos.map((video) => video.id), adapter: item.adapter },
      newIdempotencyKey(),
    );
    queued += jobs.length;
  }
  return queued;
}
