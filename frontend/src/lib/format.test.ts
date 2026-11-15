import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatDuration,
  formatFps,
  formatResolution,
  formatScore,
  formatTimestamp,
  percent,
} from "./format";

describe("formatTimestamp", () => {
  it("formats sub-hour timestamps as mm:ss.mmm", () => {
    expect(formatTimestamp(0)).toBe("00:00.000");
    expect(formatTimestamp(7.25)).toBe("00:07.250");
    expect(formatTimestamp(127.25)).toBe("02:07.250");
    expect(formatTimestamp(59.9996)).toBe("01:00.000");
  });

  it("formats timestamps of one hour or more as hh:mm:ss.mmm", () => {
    expect(formatTimestamp(3600)).toBe("01:00:00.000");
    expect(formatTimestamp(3727.5)).toBe("01:02:07.500");
    expect(formatTimestamp(45296.001)).toBe("12:34:56.001");
  });

  it("clamps negative values and handles invalid input", () => {
    expect(formatTimestamp(-3)).toBe("00:00.000");
    expect(formatTimestamp(null)).toBe("—");
    expect(formatTimestamp(undefined)).toBe("—");
    expect(formatTimestamp(Number.NaN)).toBe("—");
    expect(formatTimestamp(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("formatDuration", () => {
  it("always renders hh:mm:ss", () => {
    expect(formatDuration(0)).toBe("00:00:00");
    expect(formatDuration(59)).toBe("00:00:59");
    expect(formatDuration(754)).toBe("00:12:34");
    expect(formatDuration(3661)).toBe("01:01:01");
  });

  it("rounds to the nearest second and handles invalid input", () => {
    expect(formatDuration(59.6)).toBe("00:01:00");
    expect(formatDuration(-10)).toBe("00:00:00");
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(Number.NaN)).toBe("—");
  });
});

describe("percent", () => {
  it("converts fractions to clamped percentages", () => {
    expect(percent(0)).toBe("0%");
    expect(percent(0.5)).toBe("50%");
    expect(percent(1)).toBe("100%");
    expect(percent(1.4)).toBe("100%");
    expect(percent(-0.2)).toBe("0%");
  });

  it("supports decimals and invalid input", () => {
    expect(percent(0.4267, 1)).toBe("42.7%");
    expect(percent(null)).toBe("0%");
    expect(percent(Number.NaN)).toBe("0%");
  });
});

describe("formatBytes", () => {
  it("formats byte counts with binary units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(900)).toBe("900 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(12 * 1024 * 1024)).toBe("12.0 MB");
    expect(formatBytes(3 * 1024 * 1024 * 1024)).toBe("3.0 GB");
  });

  it("handles invalid input", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(-1)).toBe("—");
    expect(formatBytes(Number.NaN)).toBe("—");
  });
});

describe("formatDate / formatDateTime", () => {
  it("formats ISO timestamps", () => {
    expect(formatDate("2026-11-05T16:05:00Z")).toContain("2026");
    expect(formatDateTime("2026-11-05T16:05:00Z")).toContain("2026");
  });

  it("returns an em dash for missing or invalid timestamps", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not-a-date")).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("2026-13-45")).toBe("—");
  });
});

describe("small media formatters", () => {
  it("formats resolution", () => {
    expect(formatResolution(1920, 1080)).toBe("1920 × 1080");
    expect(formatResolution(null, 1080)).toBe("—");
    expect(formatResolution(0, 0)).toBe("—");
  });

  it("formats scores and frame rates", () => {
    expect(formatScore(0.95)).toBe("0.950");
    expect(formatScore(Number.NaN)).toBe("—");
    expect(formatFps(29.97)).toBe("29.97 fps");
    expect(formatFps(0)).toBe("—");
  });
});
