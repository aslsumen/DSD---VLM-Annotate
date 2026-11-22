/**
 * Layout shared by every page after sign-in (Design Description v1.2, 5.1):
 * a left sidebar with Datasets / Export / Users (role-dependent), the signed-in
 * user's name and role, a theme toggle and Sign out on every page (NFR-12).
 */
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useApiData } from "../lib/hooks";
import type { Route } from "../lib/router";
import { ROLE_LABEL } from "../lib/search";
import { useSession } from "../lib/session";
import { Icon, type IconName } from "./ui";

export type Theme = "light" | "dark";
const THEME_KEY = "vlm-annotate.theme";

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const stored = window.localStorage.getItem(THEME_KEY);
      if (stored === "light" || stored === "dark") return stored;
    } catch {
      // ignore
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      // ignore
    }
  }, [theme]);
  return [theme, () => setTheme((current) => (current === "dark" ? "light" : "dark"))];
}

function section(route: Route): "datasets" | "export" | "users" | null {
  switch (route.name) {
    case "datasets":
    case "dataset":
    case "newSearch":
    case "search":
    case "review":
      return "datasets";
    case "export":
      return "export";
    case "users":
      return "users";
    default:
      return null;
  }
}

function NavLink({
  to,
  icon,
  label,
  active,
}: {
  to: string;
  icon: IconName;
  label: string;
  active: boolean;
}) {
  return (
    <a className="side-nav__link" href={to} aria-current={active ? "page" : undefined}>
      <Icon name={icon} />
      {label}
    </a>
  );
}

export function Brand({ large = false }: { large?: boolean }) {
  return (
    <span className={large ? "brand brand--large" : "brand"}>
      <span className="brand__mark" aria-hidden="true">
        <span />
      </span>
      VLM Annotate
    </span>
  );
}

export function Shell({ route, children }: { route: Route; children: ReactNode }) {
  const session = useSession();
  const [theme, toggleTheme] = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const health = useApiData((signal) => api.getHealth(signal), []);
  const active = section(route);

  useEffect(() => setMenuOpen(false), [route]);

  return (
    <div className="shell">
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className={menuOpen ? "sidebar sidebar--open" : "sidebar"}>
        <div className="sidebar__top">
          <a href="#/" className="sidebar__brand">
            <Brand />
          </a>
          <button
            type="button"
            className="btn btn-ghost btn-icon sidebar__menu"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <Icon name={menuOpen ? "cross" : "menu"} />
          </button>
        </div>
        <nav className="side-nav" aria-label="Primary">
          <NavLink to="#/" icon="datasets" label="Datasets" active={active === "datasets"} />
          {session.canManage ? (
            <>
              <NavLink to="#/export" icon="export" label="Export" active={active === "export"} />
              <NavLink to="#/users" icon="users" label="Users" active={active === "users"} />
            </>
          ) : null}
        </nav>
        <div className="sidebar__bottom">
          <div className="sidebar__status" title={health.error?.message}>
            <span
              className={
                health.data ? "dot dot--ok" : health.error ? "dot dot--bad" : "dot dot--idle"
              }
              aria-hidden="true"
            />
            {health.data
              ? `API ${health.data.status} · model ${health.data.adapter}`
              : health.error
                ? "API unreachable"
                : "Checking API…"}
          </div>
          <div className="sidebar__user">
            {session.user ? (
              <>
                <div className="sidebar__name">{session.user.full_name || session.user.email}</div>
                <div className="muted small">{ROLE_LABEL[session.user.role]}</div>
              </>
            ) : (
              <>
                <div className="sidebar__name">Development mode</div>
                <div className="muted small">Sign-in not required · full access</div>
              </>
            )}
          </div>
          <div className="sidebar__actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} size={14} />
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            {session.user ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => void session.signOut()}>
                Sign out
              </button>
            ) : (
              <a className="btn btn-ghost btn-sm" href="#/signin">
                Sign in
              </a>
            )}
          </div>
        </div>
      </aside>
      <main id="main" className="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
