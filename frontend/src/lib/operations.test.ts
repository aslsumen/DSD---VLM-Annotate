import { afterEach, describe, expect, it, vi } from "vitest";

import type { ActionDefinition, Job } from "../types";
import { api } from "./api";
import { prepareSearch } from "./operations";

const input = { name: "Wave", description: "A person waves at the camera." };
const action: ActionDefinition = {
  id: 12,
  project_id: 4,
  ...input,
  created_at: "2026-11-20T12:00:00Z",
  updated_at: "2026-11-20T12:00:00Z",
};

describe("search launch", () => {
  afterEach(() => vi.restoreAllMocks());

  it("retries a failed enqueue with the same saved action, payload and idempotency key", async () => {
    const create = vi.spyOn(api, "createAction").mockResolvedValue(action);
    const enqueue = vi.spyOn(api, "createActionJobs")
      .mockRejectedValueOnce(new Error("Response lost"))
      .mockResolvedValueOnce([{ id: 1 } as Job]);

    const launch = await prepareSearch(action.project_id, input, "mock");
    await expect(launch.enqueue()).rejects.toThrow("Response lost");
    expect(launch.action).toBe(action);
    await launch.enqueue();

    expect(create).toHaveBeenCalledExactlyOnceWith(action.project_id, input);
    expect(enqueue).toHaveBeenCalledTimes(2);
    expect(enqueue).toHaveBeenNthCalledWith(1, action.project_id, action.id, { adapter: "mock" }, expect.any(String));
    expect(enqueue.mock.calls[1]).toEqual(enqueue.mock.calls[0]);
  });

  it("does not report a successful launch when the server queued no jobs", async () => {
    vi.spyOn(api, "createAction").mockResolvedValue(action);
    vi.spyOn(api, "createActionJobs").mockResolvedValue([]);

    const launch = await prepareSearch(action.project_id, input, "mock");
    await expect(launch.enqueue()).rejects.toMatchObject({ code: "NO_READY_VIDEOS" });
  });

  it("does not enqueue anything when saving the action fails", async () => {
    vi.spyOn(api, "createAction").mockRejectedValue(new Error("Save failed"));
    const enqueue = vi.spyOn(api, "createActionJobs");

    await expect(prepareSearch(action.project_id, input, "mock")).rejects.toThrow("Save failed");
    expect(enqueue).not.toHaveBeenCalled();
  });
});
