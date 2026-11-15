import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ReviewPage } from "./pages/ReviewPage";
import { api, getStoredToken, storeToken } from "./lib/api";
import { useApiData } from "./lib/hooks";
import { useRoute } from "./lib/router";
import { StatusChip } from "./components/ui";

function NotFoundPage({ pathname }: { pathname: string }) {
  return (
    <section className="card not-found">
      <h1>Page not found</h1>
      <p>
        There is no screen at <code>{pathname}</code>.
      </p>
      <p>
        <a className="btn btn--primary" href="#/">
          Back to projects
        </a>
      </p>
    </section>
  );
}

function App() {
  const route = useRoute();
  // Bumping this after saving a token remounts the page so every request is
  // retried with the new Authorization header.
  const [session, setSession] = useState(0);
  const health = useApiData((signal) => api.getHealth(signal), [session]);
  const adapters = useApiData((signal) => api.listAdapters(signal), [session]);

  const [tokenDraft, setTokenDraft] = useState(() => getStoredToken());
  const [tokenMessage, setTokenMessage] = useState("");

  const routeKey = JSON.stringify(route);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [routeKey]);

  const defaultAdapter =
    adapters.data?.adapters.find((adapter) => adapter.name === adapters.data?.default) ?? null;

  function handleTokenSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    storeToken(tokenDraft);
    setTokenDraft(getStoredToken());
    setSession((current) => current + 1);
    setTokenMessage(
      tokenDraft.trim()
        ? "Token saved in localStorage. Requests now send Authorization: Bearer <token>."
        : "Token cleared. Requests are sent without an Authorization header.",
    );
  }

  return (
    <>
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

      <header className="site-header">
        <div className="container site-header__inner">
          <a className="brand" href="#/">
            <span className="brand__mark" aria-hidden="true">
              VA
            </span>
            <span className="brand__text">
              <span className="brand__name">VLM Annotate</span>
              <span className="brand__tagline">Candidate review for long video</span>
            </span>
          </a>

          <nav className="site-nav" aria-label="Primary">
            <a href="#/">Projects</a>
            <a href="/api/docs" target="_blank" rel="noreferrer">
              API docs
            </a>
          </nav>

          <div className="header-status" aria-label="API status">
            {health.loading && !health.data ? (
              <span className="chip chip--neutral">Checking API…</span>
            ) : null}

            {health.error && !health.data ? (
              <>
                <span className="chip chip--danger" title={health.error.message}>
                  API unreachable
                </span>
                <button
                  type="button"
                  className="btn btn--ghost btn--small"
                  onClick={() => {
                    health.reload();
                    adapters.reload();
                  }}
                >
                  Retry
                </button>
              </>
            ) : null}

            {health.data ? (
              <span
                className="chip chip--ok"
                title={`${health.data.app} ${health.data.version} · ${health.data.environment} · ${health.data.database}`}
              >
                API {health.data.status} · v{health.data.version}
              </span>
            ) : null}

            {adapters.data ? (
              <span className="header-status__text">
                Adapter{" "}
                <strong>{adapters.data.default}</strong>{" "}
                {defaultAdapter ? (
                  <StatusChip
                    status={defaultAdapter.available ? "ready" : "failed"}
                    label={defaultAdapter.available ? "available" : "unavailable"}
                  />
                ) : null}
              </span>
            ) : null}

            {adapters.error ? (
              <span className="header-status__text" title={adapters.error.message}>
                Adapter status unavailable
              </span>
            ) : null}
          </div>

          <details className="token">
            <summary>API token</summary>
            <form className="token__form" onSubmit={handleTokenSubmit}>
              <label htmlFor="api-token">Bearer token</label>
              <p className="field__hint">
                Only needed when the deployment sets <code>VLM_API_TOKEN</code>. Stored in this
                browser&apos;s localStorage and sent as{" "}
                <code>Authorization: Bearer &lt;token&gt;</code>.
              </p>
              <input
                id="api-token"
                name="api-token"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={tokenDraft}
                onChange={(event) => setTokenDraft(event.target.value)}
                placeholder="Paste the deployment token"
              />
              <div className="row">
                <button type="submit" className="btn btn--primary btn--small">
                  Save token
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--small"
                  onClick={() => {
                    setTokenDraft("");
                    storeToken("");
                    setSession((current) => current + 1);
                    setTokenMessage("Token cleared.");
                  }}
                >
                  Clear
                </button>
              </div>
              {tokenMessage ? (
                <p className="field__hint" role="status">
                  {tokenMessage}
                </p>
              ) : null}
            </form>
          </details>
        </div>
      </header>

      <main id="main" className="container main" tabIndex={-1}>
        {route.name === "projects" ? <ProjectsPage key={`projects-${session}`} /> : null}

        {route.name === "project" ? (
          <ProjectPage
            key={`project-${route.projectId}-${session}`}
            projectId={route.projectId}
          />
        ) : null}

        {route.name === "review" ? (
          <ReviewPage
            key={`review-${route.projectId}-${route.jobId ?? "none"}-${session}`}
            projectId={route.projectId}
            jobId={route.jobId}
          />
        ) : null}

        {route.name === "notFound" ? <NotFoundPage pathname={route.pathname} /> : null}
      </main>

      <footer className="site-footer">
        <div className="container site-footer__inner">
          <p>VLM Annotate · university DSD project</p>
          <p className="muted">
            Candidates produced by the <code>mock</code> adapter are clearly flagged: they are not
            based on video pixels.
          </p>
        </div>
      </footer>
    </>
  );
}

export default App;
