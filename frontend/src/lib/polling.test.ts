import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { schedulePoll } from "./polling";

describe("search polling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("waits for a slow request to settle and schedules only one refresh", () => {
    const reload = vi.fn();
    schedulePoll({ active: true, loading: true }, 2500, reload);
    vi.advanceTimersByTime(7500);
    expect(reload).not.toHaveBeenCalled();

    schedulePoll({ active: true, loading: false }, 2500, reload);
    vi.advanceTimersByTime(2499);
    expect(reload).not.toHaveBeenCalled();
    vi.advanceTimersByTime(7501);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("cancels a scheduled refresh on navigation and does not poll a terminal search", () => {
    const reload = vi.fn();
    const cancel = schedulePoll({ active: true, loading: false }, 3000, reload);
    expect(cancel).toBeTypeOf("function");
    cancel?.();
    schedulePoll({ active: false, loading: false }, 3000, reload);
    vi.advanceTimersByTime(6000);
    expect(reload).not.toHaveBeenCalled();
  });

  it.each([401, 403])("does not re-schedule polling after HTTP %i", (status) => {
    const reload = vi.fn();
    schedulePoll({ active: true, loading: false, status }, 2500, reload);
    vi.advanceTimersByTime(7500);
    expect(reload).not.toHaveBeenCalled();
  });

  it("retries a transient error on an active search", () => {
    const reload = vi.fn();
    schedulePoll({ active: true, loading: false, status: 503 }, 2500, reload);
    vi.advanceTimersByTime(2500);
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
