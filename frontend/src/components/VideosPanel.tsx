import type { FormEvent } from "react";
import { useRef, useState } from "react";

import { EmptyState, ErrorNotice, StatusChip } from "../components/ui";
import { api, toApiError } from "../lib/api";
import type { ApiError } from "../lib/api";
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatFps,
  formatResolution,
  percent,
} from "../lib/format";
import type { Video } from "../types";

const ACCEPTED_TYPES =
  "video/mp4,video/quicktime,video/x-m4v,video/webm,video/x-matroska,.mp4,.mov,.m4v,.webm,.mkv";

interface VideosPanelProps {
  projectId: number;
  videos: Video[];
  onChanged: () => void;
  onNotify: (text: string, tone: "ok" | "danger") => void;
}

export function VideosPanel({ projectId, videos, onChanged, onNotify }: VideosPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      return;
    }
    setError(null);
    setUploading(true);
    setUploadProgress(0);
    try {
      const video = await api.uploadVideo(projectId, file, (fraction) =>
        setUploadProgress(fraction),
      );
      onNotify(
        `Uploaded "${video.original_filename}" (${formatDuration(video.duration_seconds)}, ${video.status}).`,
        "ok",
      );
      setFile(null);
      setUploadProgress(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
      onChanged();
    } catch (failure) {
      setUploadProgress(null);
      setError(toApiError(failure));
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="card panel" aria-labelledby="videos-heading">
      <div className="panel__head">
        <h2 id="videos-heading">Videos</h2>
        <p className="muted">
          Single-view RGB recordings, ideally 10–30 minutes long. The server probes each file and
          only marks it ready when it can be decoded.
        </p>
      </div>

      <form className="form upload-form" onSubmit={(event) => void handleUpload(event)}>
        <div className="field">
          <label htmlFor="video-file">Video file</label>
          <input
            ref={inputRef}
            id="video-file"
            name="file"
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError(null);
            }}
            disabled={uploading}
          />
          <p className="field__hint">
            Accepted containers: mp4, mov, m4v, webm, mkv. Files stay on the server; nothing is
            uploaded anywhere else.
          </p>
        </div>

        {file ? (
          <p className="meta">
            Selected: <strong>{file.name}</strong> · {formatBytes(file.size)}
          </p>
        ) : null}

        {uploadProgress !== null ? (
          <div className="upload-progress">
            <progress
              max={100}
              value={Math.round(uploadProgress * 100)}
              aria-label="Upload progress"
              aria-describedby="upload-progress-text"
            />
            <span id="upload-progress-text" className="meta">
              {percent(uploadProgress)} uploaded
            </span>
          </div>
        ) : null}

        {error ? <ErrorNotice error={error} title="Upload failed" /> : null}

        <button type="submit" className="btn btn--primary btn--small" disabled={!file || uploading}>
          {uploading ? "Uploading…" : "Upload video"}
        </button>
      </form>

      {videos.length === 0 ? (
        <EmptyState title="No videos uploaded">
          <p>
            Upload a single-view RGB video above. Once it is <strong>ready</strong> you can queue a
            VLM processing job for it.
          </p>
        </EmptyState>
      ) : (
        <>
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Videos table; scroll sideways on narrow screens"
          >
            <table className="table">
              <caption className="sr-only">Videos uploaded to this project</caption>
              <thead>
                <tr>
                  <th scope="col">File</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Resolution</th>
                  <th scope="col">FPS</th>
                  <th scope="col">Status</th>
                  <th scope="col">Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {videos.map((video) => (
                  <tr key={video.id}>
                    <td>
                      <span className="filename">{video.original_filename}</span>
                      <span className="meta block">{formatBytes(video.size_bytes)}</span>
                      {video.error_message ? (
                        <span className="error-text block">{video.error_message}</span>
                      ) : null}
                    </td>
                    <td>
                      <span title={`${video.duration_seconds ?? "—"} seconds`}>
                        {formatDuration(video.duration_seconds)}
                      </span>
                    </td>
                    <td>{formatResolution(video.width, video.height)}</td>
                    <td>{formatFps(video.fps)}</td>
                    <td>
                      <StatusChip status={video.status} />
                    </td>
                    <td>{formatDateTime(video.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta table-hint">Scroll sideways to see every column.</p>
        </>
      )}
    </section>
  );
}
