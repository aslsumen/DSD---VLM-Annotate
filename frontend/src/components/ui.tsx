import type { ReactNode } from "react";

import type { ApiError } from "../lib/api";
import { formatTimestamp, percent } from "../lib/format";

export type Tone = "ok" | "warn" | "danger" | "info" | "neutral" | "muted";

const STATUS_TONES: Record<string, Tone> = {
  // Jobs and exports
  queued: "neutral",
  running: "info",
  succeeded: "ok",
  failed: "danger",
  canceled: "muted",
  // Videos and clips
  uploaded: "warn",
  ready: "ok",
  pending: "warn",
  skipped: "muted",
  // Review
  unreviewed: "warn",
  reviewed: "ok",
  true_positive: "ok",
  false_positive: "danger",
};

const STATUS_LABELS: Record<string, string> = {
  true_positive: "True positive",
  false_positive: "False positive",
  candidate_proposal: "Candidate proposal",
  dataset_export: "Dataset export",
};

const CHIP_CLASS: Record<Tone, string> = {
  ok: "chip chip--ok",
  warn: "chip chip--warn",
  danger: "chip chip--danger",
  info: "chip chip--info",
  neutral: "chip chip--neutral",
  muted: "chip chip--muted",
};

export function StatusChip({ status, label }: { status: string; label?: string }) {
  const tone = STATUS_TONES[status] ?? "neutral";
  const text = label ?? STATUS_LABELS[status] ?? status.replaceAll("_", " ");
  return <span className={CHIP_CLASS[tone]}>{text}</span>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </p>
  );
}

export function ErrorNotice({
  error,
  onRetry,
  title = "Something went wrong",
}: {
  error: ApiError;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div className="banner banner--danger" role="alert">
      <div className="banner__content">
        <strong>{title}</strong>
        <p>
          <code className="error-code">{error.code}</code> {error.message}
        </p>
        {error.isUnauthenticated ? (
          <p className="banner__hint">
            This deployment requires a bearer token. Open <strong>API token</strong> in the
            header, paste the token and save it.
          </p>
        ) : null}
      </div>
      {onRetry ? (
        <button type="button" className="btn btn--ghost btn--small" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Notice({
  tone,
  children,
  onDismiss,
}: {
  tone: "ok" | "danger" | "info";
  children: ReactNode;
  onDismiss?: () => void;
}) {
  const toneClass = tone === "ok" ? "banner--ok" : tone === "danger" ? "banner--danger" : "banner--info";
  return (
    <div className={`banner ${toneClass}`} role={tone === "danger" ? "alert" : "status"}>
      <div className="banner__content">{children}</div>
      {onDismiss ? (
        <button type="button" className="btn btn--ghost btn--small" onClick={onDismiss}>
          Dismiss
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      {children ? <div className="empty__body">{children}</div> : null}
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <strong className="stat__value">{value}</strong>
      {hint ? <span className="stat__hint">{hint}</span> : null}
    </div>
  );
}

/** Timestamp with the exact seconds exposed in the tooltip. */
export function Timestamp({ seconds }: { seconds: number | null | undefined }) {
  const exact = seconds === null || seconds === undefined ? "—" : `${seconds} s`;
  return (
    <span className="timestamp" title={`${exact} from the start of the source video`}>
      {formatTimestamp(seconds)}
    </span>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const safe = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(safe * 100)}
      aria-valuetext={percent(safe)}
    >
      <div className="progress__fill" style={{ width: percent(safe) }} />
    </div>
  );
}

/** Visually hidden live region for asynchronous announcements. */
export function AriaLive({ message }: { message: string }) {
  return (
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {message}
    </p>
  );
}
