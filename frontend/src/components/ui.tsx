/**
 * Shared presentational components (Industry design system from the Claude
 * mockup: Barlow Condensed over Barlow, steel-blue accent, square hairline
 * "blueprint" frames with registration corners).
 */
import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

import type { ApiError } from "../lib/api";
import { percent } from "../lib/format";
import type { ReviewStatus, SearchStatus } from "../lib/search";

// --------------------------------------------------------------------------- //
// Icons (stroke icons, 24-unit grid)
// --------------------------------------------------------------------------- //

const ICONS = {
  datasets: (
    <>
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5v14a9 3 0 0 0 18 0V5" />
      <path d="M3 12a9 3 0 0 0 18 0" />
    </>
  ),
  export: (
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M7 10l5 5 5-5" />
      <path d="M12 15V3" />
    </>
  ),
  users: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </>
  ),
  plus: <path d="M5 12h14M12 5v14" />,
  search: (
    <>
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </>
  ),
  back: <path d="m12 19-7-7 7-7M19 12H5" />,
  upload: (
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M17 8l-5-5-5 5" />
      <path d="M12 3v12" />
    </>
  ),
  film: (
    <>
      <rect x="2" y="2" width="20" height="20" rx="2" />
      <path d="M7 2v20M17 2v20M2 12h20" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </>
  ),
  check: <path d="M20 6 9 17l-5-5" />,
  cross: <path d="M18 6 6 18M6 6l12 12" />,
  alert: (
    <>
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
      <path d="M12 9v4M12 17h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4M12 16h.01" />
    </>
  ),
  spinner: <path d="M21 12a9 9 0 1 1-6.219-8.56" />,
  restart: (
    <>
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
    </>
  ),
  keyboard: (
    <>
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10" />
    </>
  ),
  play: <path d="M7 4v16l13-8z" />,
  pause: <path d="M7 4h3v16H7zM14 4h3v16h-3z" />,
  lock: (
    <>
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </>
  ),
  trash: (
    <>
      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
    </>
  ),
  copy: (
    <>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>
  ),
  moon: <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z" />,
  menu: <path d="M3 6h18M3 12h18M3 18h18" />,
} as const;

export type IconName = keyof typeof ICONS;

export function Icon({
  name,
  size = 16,
  spin = false,
  className,
}: {
  name: IconName;
  size?: number;
  spin?: boolean;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={["icon", spin ? "icon--spin" : "", className ?? ""].join(" ").trim()}
      aria-hidden="true"
      focusable="false"
    >
      {ICONS[name]}
    </svg>
  );
}

// --------------------------------------------------------------------------- //
// Frames and layout
// --------------------------------------------------------------------------- //

export function Corners() {
  return (
    <>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
    </>
  );
}

/** Hairline box with registration corners (`.blueprint` in the design system). */
export function Frame({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "aside";
}) {
  return (
    <Tag className={["blueprint", className ?? ""].join(" ").trim()}>
      <Corners />
      {children}
    </Tag>
  );
}

export function PageHeader({
  kicker,
  title,
  subtitle,
  actions,
  back,
}: {
  kicker?: string;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="page-header">
      {back ? (
        <a className="btn btn-ghost back-link" href={back.href}>
          <Icon name="back" size={14} />
          {back.label}
        </a>
      ) : null}
      <div className="page-header__row">
        <div className="page-header__text">
          {kicker ? <div className="kicker">{kicker}</div> : null}
          <h1>{title}</h1>
          {subtitle ? <div className="muted">{subtitle}</div> : null}
        </div>
        {actions ? <div className="page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}

// --------------------------------------------------------------------------- //
// Status
// --------------------------------------------------------------------------- //

const SEARCH_LABEL: Record<SearchStatus, string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  partial: "Partial",
  failed: "Failed",
  empty: "No videos",
};

/** Search status chip (DET-3): colour, icon and label each carry the state. */
export function SearchChip({ status, progress }: { status: SearchStatus; progress?: number }) {
  const icon: IconName =
    status === "running"
      ? "spinner"
      : status === "done"
        ? "check"
        : status === "failed" || status === "partial"
          ? "alert"
          : "clock";
  return (
    <span className={`chip chip--${status}`}>
      <Icon name={icon} size={13} spin={status === "running"} />
      {SEARCH_LABEL[status]}
      {status === "running" && progress !== undefined ? ` ${percent(progress)}` : ""}
    </span>
  );
}

const REVIEW_LABEL: Record<ReviewStatus, string> = {
  unreviewed: "Unreviewed",
  accepted: "Accepted",
  rejected: "Rejected",
};

export function ReviewChip({ status }: { status: ReviewStatus }) {
  return (
    <span className={`chip chip--${status}`}>
      {status === "accepted" ? <Icon name="check" size={12} /> : null}
      {status === "rejected" ? <Icon name="cross" size={12} /> : null}
      {REVIEW_LABEL[status]}
    </span>
  );
}

export function ProgressBar({
  value,
  label,
  thick = false,
}: {
  value: number;
  label: string;
  thick?: boolean;
}) {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
  return (
    <div
      className={thick ? "bar bar--thick" : "bar"}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped * 100)}
    >
      <div className="bar__fill" style={{ width: percent(clamped, 1) }} />
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <Icon name="spinner" spin size={16} />
      <span>{label}</span>
    </div>
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
    <div className="notice notice--danger" role="alert">
      <Icon name="alert" size={18} />
      <div className="notice__body">
        <div className="notice__title">{title}</div>
        <div>{error.message}</div>
        {error.code && error.code !== "CLIENT_ERROR" ? (
          <div className="notice__code">{error.code}</div>
        ) : null}
      </div>
      {onRetry ? (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warning" | "danger" | "ok";
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "danger" ? "alert" : "note"}>
      <Icon name={tone === "ok" ? "check" : tone === "info" ? "info" : "alert"} size={18} />
      <div className="notice__body">
        {title ? <div className="notice__title">{title}</div> : null}
        <div>{children}</div>
      </div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty__title">{title}</div>
      {children ? <div className="muted">{children}</div> : null}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Dialog
// --------------------------------------------------------------------------- //

export function Dialog({
  title,
  children,
  actions,
  onClose,
}: {
  title: string;
  children: ReactNode;
  actions: ReactNode;
  onClose: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const first = panel.current?.querySelector<HTMLElement>(
      "input, textarea, select, button:not([disabled])",
    );
    first?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div
        ref={panel}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog-title">{title}</div>
        <div className="dialog-body">{children}</div>
        <div className="dialog-actions">{actions}</div>
      </div>
    </div>
  );
}

/** Polite live region for announcements that are not otherwise visible. */
export function AriaLive({ message }: { message: string }) {
  return (
    <div className="sr-only" aria-live="polite" role="status">
      {message}
    </div>
  );
}

export function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, 3500);
    return () => window.clearTimeout(timer);
  }, [message, onDone]);
  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  );
}
