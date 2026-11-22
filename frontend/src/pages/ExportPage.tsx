/**
 * Export view (EXP-1, EXP-2; Design Description v1.2, 5.5). Administrators and
 * Dataset Administrators only.
 *
 * 1. JSON annotations: built in the browser from the reviewed candidates, in the
 *    first-proposal format of Design 4.3, until the OpenLABEL-based schema and its
 *    backend endpoint exist. Unreviewed candidates are never exported.
 * 2. Dataset package: the existing asynchronous ZIP export (manifest.json,
 *    labels.csv, clips) produced by the worker.
 */
import { useEffect, useMemo, useState } from "react";

import { ErrorNotice, Frame, Icon, Loading, Notice, PageHeader } from "../components/ui";
import { api, downloadExportFile, toApiError, type ApiError } from "../lib/api";
import { formatBytes, formatDateTime } from "../lib/format";
import { useApiData } from "../lib/hooks";
import { buildExportDocument, countReview, summarizeSearch } from "../lib/search";
import type { DatasetExport } from "../types";

async function loadDataset(projectId: number, signal: AbortSignal) {
  const [project, actions, videos, candidates, jobs, exports] = await Promise.all([
    api.getProject(projectId, signal),
    api.listActions(projectId, signal),
    api.listVideos(projectId, signal),
    api.projectCandidates(projectId, {}, signal),
    api.listJobs({ projectId, limit: 200 }, signal),
    api.listExports(projectId, signal),
  ]);
  return { project, actions, videos, candidates, jobs, exports };
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "dataset";
}

function saveJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

const EXPORT_LABEL: Record<DatasetExport["status"], string> = {
  queued: "Queued",
  running: "Building",
  ready: "Ready",
  failed: "Failed",
};

export function ExportPage({ initialDatasetId }: { initialDatasetId: number | null }) {
  const projects = useApiData((signal) => api.listProjects(signal), []);
  const [datasetId, setDatasetId] = useState<number | null>(initialDatasetId);
  const [searchId, setSearchId] = useState<number | "all">("all");
  const [includeRejected, setIncludeRejected] = useState(false);
  const [includeUnreviewedZip, setIncludeUnreviewedZip] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (datasetId === null && projects.data && projects.data.length > 0) {
      setDatasetId(projects.data[0].id);
    }
  }, [projects.data, datasetId]);

  const dataset = useApiData(
    (signal) => (datasetId ? loadDataset(datasetId, signal) : Promise.resolve(null)),
    [datasetId],
  );

  const hasRunningExport = dataset.data?.exports.some((item) => item.status === "queued" || item.status === "running");
  const reload = dataset.reload;
  useEffect(() => {
    if (!hasRunningExport) return undefined;
    const timer = window.setInterval(reload, 2500);
    return () => window.clearInterval(timer);
  }, [hasRunningExport, reload]);

  const rows = useMemo(() => {
    if (!dataset.data) return [];
    return dataset.data.actions.map((action) => {
      const candidates = dataset.data!.candidates.filter((candidate) => candidate.action_id === action.id);
      const adapters = summarizeSearch(dataset.data!.jobs.filter((job) => job.action_id === action.id)).adapters;
      return { action, candidates, adapters, counts: countReview(candidates) };
    });
  }, [dataset.data]);

  const chosen = searchId === "all" ? rows : rows.filter((row) => row.action.id === searchId);
  const totals = chosen.reduce(
    (sum, row) => ({
      accepted: sum.accepted + row.counts.accepted,
      rejected: sum.rejected + row.counts.rejected,
      unreviewed: sum.unreviewed + row.counts.unreviewed,
    }),
    { accepted: 0, rejected: 0, unreviewed: 0 },
  );
  const nothing = totals.accepted + (includeRejected ? totals.rejected : 0) === 0;

  function downloadJson() {
    if (!dataset.data) return;
    const doc = buildExportDocument(dataset.data.project, chosen, dataset.data.videos, includeRejected);
    const suffix = searchId === "all" ? "all-searches" : slug(chosen[0]?.action.name ?? "search");
    saveJson(`${slug(dataset.data.project.name)}-${suffix}${includeRejected ? "-with-rejected" : ""}.json`, doc);
  }

  async function buildZip() {
    if (!datasetId) return;
    setBusy(true);
    setError(null);
    try {
      await api.createExport(datasetId, { include_unreviewed: includeUnreviewedZip });
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setBusy(false);
      reload();
    }
  }

  async function downloadZip(item: DatasetExport) {
    setError(null);
    try {
      await downloadExportFile(item.id, `${slug(dataset.data?.project.name ?? "dataset")}-export-${item.id}.zip`);
    } catch (failure) {
      setError(toApiError(failure));
    }
  }

  return (
    <div className="page page--wide">
      <PageHeader
        kicker="Export"
        title="Export annotations"
        subtitle="A JSON file with the accepted annotations. Unreviewed candidates are never exported."
      />
      {projects.error ? <ErrorNotice error={projects.error} onRetry={projects.reload} /> : null}
      {projects.data && projects.data.length === 0 ? (
        <Notice>There is no dataset to export yet.</Notice>
      ) : null}

      {projects.data && projects.data.length > 0 ? (
        <div className="export-grid">
          <Frame className="form-frame">
            <div className="stack">
              <div className="stack-sm">
                <span className="label">Dataset</span>
                <div className="radio-list" role="radiogroup" aria-label="Dataset">
                  {projects.data.map((project) => (
                    <button
                      key={project.id}
                      type="button"
                      role="radio"
                      aria-checked={datasetId === project.id}
                      className={datasetId === project.id ? "radio-item is-on" : "radio-item"}
                      onClick={() => {
                        setDatasetId(project.id);
                        setSearchId("all");
                      }}
                    >
                      <span className="radio-item__dot" />
                      <span className="radio-item__label">{project.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {dataset.data && rows.length > 0 ? (
                <div className="stack-sm">
                  <span className="label">Search</span>
                  <div className="chips-row">
                    <button
                      type="button"
                      className={searchId === "all" ? "pill is-on" : "pill"}
                      onClick={() => setSearchId("all")}
                    >
                      All searches
                    </button>
                    {rows.map((row) => (
                      <button
                        key={row.action.id}
                        type="button"
                        className={searchId === row.action.id ? "pill is-on" : "pill"}
                        onClick={() => setSearchId(row.action.id)}
                      >
                        {row.action.name}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <button
                type="button"
                role="switch"
                aria-checked={includeRejected}
                className="switch"
                onClick={() => setIncludeRejected((value) => !value)}
              >
                <span className="switch__track">
                  <span className="switch__thumb" />
                </span>
                <span className="stack-xs">
                  <span className="strong">Include rejected candidates as negatives</span>
                  <span className="muted small">Optional (EXP-2). Useful for training with hard negatives.</span>
                </span>
              </button>

              <div className="form-actions">
                <button type="button" className="btn btn-primary btn-lg" disabled={nothing || !dataset.data} onClick={downloadJson}>
                  <Icon name="export" />
                  Download JSON
                </button>
                <span className="muted small">Based on the Design 4.3 proposal · OpenLABEL structure to be confirmed</span>
              </div>
            </div>
          </Frame>

          <section className="stack">
            <h3>In this export</h3>
            {dataset.loading && !dataset.data ? <Loading /> : null}
            {dataset.error ? <ErrorNotice error={dataset.error} onRetry={reload} /> : null}
            {dataset.data ? (
              <>
                <div className="figures">
                  <div>
                    <span className="figure ok-ink">{totals.accepted}</span>
                    <span className="muted small">Accepted · included</span>
                  </div>
                  <div>
                    <span className="figure bad-ink">{totals.rejected}</span>
                    <span className="muted small">Rejected · {includeRejected ? "included" : "left out"}</span>
                  </div>
                  <div>
                    <span className="figure">{totals.unreviewed}</span>
                    <span className="muted small">Unreviewed · not exported</span>
                  </div>
                </div>
                {rows.length > 0 ? (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Search</th>
                          <th className="right">Accepted</th>
                          <th className="right">Rejected</th>
                          <th className="right">Unreviewed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr key={row.action.id}>
                            <td>{row.action.name}</td>
                            <td className="right tabular">{row.counts.accepted}</td>
                            <td className="right tabular">{row.counts.rejected}</td>
                            <td className="right tabular">{row.counts.unreviewed}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Notice>This dataset has no search yet.</Notice>
                )}
                {nothing && rows.length > 0 ? (
                  <div className="muted small">Nothing to export yet — accept some candidates first.</div>
                ) : null}
              </>
            ) : null}
          </section>
        </div>
      ) : null}

      {dataset.data ? (
        <section className="stack">
          <div className="section-title">
            <h3>Dataset package (ZIP)</h3>
          </div>
          <p className="muted small">
            Built by the worker: <code>manifest.json</code> with full provenance, <code>labels.csv</code> and one
            MP4 clip per reviewed candidate. It includes accepted and rejected decisions.
          </p>
          {error ? <ErrorNotice error={error} title="Export action failed" /> : null}
          <div className="row">
            <label className="check small">
              <input
                type="checkbox"
                checked={includeUnreviewedZip}
                onChange={(event) => setIncludeUnreviewedZip(event.target.checked)}
              />
              Also include unreviewed candidates, marked as unreviewed
            </label>
            <button type="button" className="btn btn-secondary push-right" disabled={busy} onClick={() => void buildZip()}>
              {busy ? "Queuing…" : "Build package"}
            </button>
          </div>
          {dataset.data.exports.length > 0 ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Package</th>
                    <th>Status</th>
                    <th className="right">Items</th>
                    <th className="right">Size</th>
                    <th>Created</th>
                    <th className="right">Download</th>
                  </tr>
                </thead>
                <tbody>
                  {dataset.data.exports.map((item) => (
                    <tr key={item.id}>
                      <td className="tabular">
                        #{item.id}
                        {item.include_unreviewed ? <span className="muted small"> · with unreviewed</span> : null}
                      </td>
                      <td>
                        <span className={`chip chip--export-${item.status}`} title={item.error_message ?? undefined}>
                          {EXPORT_LABEL[item.status]}
                        </span>
                      </td>
                      <td className="right tabular">{item.item_count}</td>
                      <td className="right tabular">{formatBytes(item.size_bytes)}</td>
                      <td className="muted small">{formatDateTime(item.created_at)}</td>
                      <td className="right">
                        {item.status === "ready" && item.has_file ? (
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void downloadZip(item)}>
                            Download
                          </button>
                        ) : (
                          <span className="muted small">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
