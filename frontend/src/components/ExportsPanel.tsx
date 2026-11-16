import { useState } from "react";

import { EmptyState, ErrorNotice, StatusChip } from "../components/ui";
import { api, downloadExportFile, toApiError, type ApiError } from "../lib/api";
import { formatBytes, formatDateTime } from "../lib/format";
import type { DatasetExport } from "../types";

interface ExportsPanelProps {
  projectId: number;
  exports: DatasetExport[];
  onChanged: () => void;
  onNotify: (text: string, tone: "ok" | "danger") => void;
}

export function ExportsPanel({ projectId, exports, onChanged, onNotify }: ExportsPanelProps) {
  const [includeUnreviewed, setIncludeUnreviewed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  async function handleCreate() {
    setError(null);
    setCreating(true);
    try {
      const created = await api.createExport(projectId, { include_unreviewed: includeUnreviewed });
      onNotify(
        `Export #${created.export.id} queued (${created.export.include_unreviewed ? "includes" : "excludes"} unreviewed candidates).`,
        "ok",
      );
      onChanged();
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setCreating(false);
    }
  }

  async function handleDownload(datasetExport: DatasetExport) {
    setDownloadingId(datasetExport.id);
    setError(null);
    try {
      await downloadExportFile(
        datasetExport.id,
        `vlm-annotate-project-${projectId}-export-${datasetExport.id}.zip`,
      );
      onNotify(`Export #${datasetExport.id} downloaded.`, "ok");
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <section className="card panel" aria-labelledby="exports-heading">
      <div className="panel__head">
        <h2 id="exports-heading">Dataset exports</h2>
        <p className="muted">
          A ZIP with <code>manifest.json</code>, <code>labels.csv</code>, a README and the reviewed
          clip files.
        </p>
      </div>

      <div className="form">
        <div className="checkbox-field">
          <input
            id="include-unreviewed"
            name="include-unreviewed"
            type="checkbox"
            checked={includeUnreviewed}
            onChange={(event) => setIncludeUnreviewed(event.target.checked)}
          />
          <label htmlFor="include-unreviewed">Include unreviewed candidates</label>
        </div>

        {includeUnreviewed ? (
          <p className="field__hint field__hint--warn">
            Unreviewed candidates have no verdict. They are exported with{" "}
            <code>verdict: &quot;unreviewed&quot;</code> and{" "}
            <code>review_state: &quot;unreviewed&quot;</code> — only use this for an explicitly
            unlabelled snapshot.
          </p>
        ) : (
          <p className="field__hint">
            Without this option the export only contains candidates you have reviewed. Exporting
            with none reviewed is rejected.
          </p>
        )}

        {error ? <ErrorNotice error={error} title="Export failed" /> : null}

        <button
          type="button"
          className="btn btn--primary btn--small"
          onClick={() => void handleCreate()}
          disabled={creating}
        >
          {creating ? "Creating export…" : "Create export"}
        </button>
      </div>

      {exports.length === 0 ? (
        <EmptyState title="No exports yet">
          <p>Review candidates first, then create an export to download the labelled dataset.</p>
        </EmptyState>
      ) : (
        <ul className="export-list">
          {exports.map((datasetExport) => (
            <li key={datasetExport.id} className="export-item">
              <div className="export-item__head">
                <h3>Export #{datasetExport.id}</h3>
                <StatusChip status={datasetExport.status} />
              </div>

              <dl className="job-meta">
                <div>
                  <dt>Format</dt>
                  <dd>{datasetExport.format.toUpperCase()}</dd>
                </div>
                <div>
                  <dt>Items</dt>
                  <dd>{datasetExport.item_count}</dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{formatBytes(datasetExport.size_bytes)}</dd>
                </div>
                <div>
                  <dt>Unreviewed</dt>
                  <dd>{datasetExport.include_unreviewed ? "included" : "excluded"}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{formatDateTime(datasetExport.created_at)}</dd>
                </div>
                {datasetExport.finished_at ? (
                  <div>
                    <dt>Finished</dt>
                    <dd>{formatDateTime(datasetExport.finished_at)}</dd>
                  </div>
                ) : null}
              </dl>

              {datasetExport.error_message ? (
                <p className="error-text">{datasetExport.error_message}</p>
              ) : null}

              <div className="row">
                {datasetExport.status === "ready" && datasetExport.has_file ? (
                  <button
                    type="button"
                    className="btn btn--primary btn--small"
                    onClick={() => void handleDownload(datasetExport)}
                    disabled={downloadingId === datasetExport.id}
                  >
                    {downloadingId === datasetExport.id
                      ? "Downloading…"
                      : `Download ZIP (${formatBytes(datasetExport.size_bytes)})`}
                  </button>
                ) : (
                  <span className="meta">
                    {datasetExport.status === "ready"
                      ? "The archive file is no longer available."
                      : "Download becomes available when the export is ready."}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
