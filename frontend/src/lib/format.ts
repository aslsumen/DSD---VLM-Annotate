/**
 * Formatting helpers for media timestamps, durations and byte sizes.
 *
 * Every helper accepts `null` / `undefined` / non-finite input and renders an
 * em dash instead of leaking `undefined` or `NaN` into the interface.
 */

const EMPTY = "—";

function pad(value: number, length = 2): string {
  return String(value).padStart(length, "0");
}

/**
 * Source-video-relative timestamp.
 *
 * Under one hour: `mm:ss.mmm` (e.g. `02:07.250`).
 * One hour or more: `hh:mm:ss.mmm` (e.g. `01:02:07.250`).
 */
export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return EMPTY;
  }
  const totalMilliseconds = Math.max(0, Math.round(seconds * 1000));
  const milliseconds = totalMilliseconds % 1000;
  const totalSeconds = Math.floor(totalMilliseconds / 1000);
  const secs = totalSeconds % 60;
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const hours = Math.floor(totalSeconds / 3600);
  const clock = `${pad(minutes)}:${pad(secs)}.${pad(milliseconds, 3)}`;
  return hours > 0 ? `${pad(hours)}:${clock}` : clock;
}

/**
 * Clock-style duration used in tables: always `hh:mm:ss` (e.g. `00:12:34`).
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return EMPTY;
  }
  const totalSeconds = Math.max(0, Math.round(seconds));
  const secs = totalSeconds % 60;
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const hours = Math.floor(totalSeconds / 3600);
  return `${pad(hours)}:${pad(minutes)}:${pad(secs)}`;
}

/**
 * Turns a 0..1 fraction into a percentage string, clamped to `0%`..`100%`.
 * Invalid input renders `0%` so progress bars never break.
 */
export function percent(fraction: number | null | undefined, digits = 0): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) {
    return "0%";
  }
  const clamped = Math.min(1, Math.max(0, fraction));
  return `${(clamped * 100).toFixed(digits)}%`;
}

/** Human-readable byte size (e.g. `1.5 MB`). */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) {
    return EMPTY;
  }
  if (bytes < 1024) {
    return `${Math.round(bytes)} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

function parseDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Local date, e.g. `5 Nov 2026`. */
export function formatDate(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) {
    return EMPTY;
  }
  return date.toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** Local date and time, e.g. `5 Nov 2026, 17:05`. */
export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) {
    return EMPTY;
  }
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** Resolution label, e.g. `1920 × 1080`; falls back to an em dash. */
export function formatResolution(width: number | null, height: number | null): string {
  if (!width || !height) {
    return EMPTY;
  }
  return `${width} × ${height}`;
}

/** Model score with a fixed precision, e.g. `0.950`. */
export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score)) {
    return EMPTY;
  }
  return score.toFixed(3);
}

/** Frame rate label, e.g. `29.97 fps`. */
export function formatFps(fps: number | null | undefined): string {
  if (fps === null || fps === undefined || !Number.isFinite(fps) || fps <= 0) {
    return EMPTY;
  }
  return `${fps.toFixed(2)} fps`;
}
