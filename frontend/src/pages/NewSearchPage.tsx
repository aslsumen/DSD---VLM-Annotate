/**
 * New search (DS-3, PR-1, PR-3, DET-3; Design Description v1.2, 5.3).
 *
 * One prompt runs on every ready video of the dataset: the client creates the
 * prompt (ActionDefinition) and queues one job per video with the batch endpoint.
 */
import { useRef, useState } from "react";

import { ErrorNotice, Frame, Loading, Notice, PageHeader } from "../components/ui";
import { api, toApiError, type ApiError } from "../lib/api";
import { useApiData } from "../lib/hooks";
import { prepareSearch } from "../lib/operations";
import { navigate } from "../lib/router";
import { promptTitle, uniqueName } from "../lib/search";

/** Example prompts from the customer (Requirements Definition v1.2, PR-1; CE). */
const EXAMPLES = [
  "A person opens a door.",
  "A person enters the zone marked by orange lines on the floor.",
  "A person is putting on a helmet.",
  "A person washes their hands at the sink.",
];

async function load(projectId: number, signal: AbortSignal) {
  const [project, videos, actions, adapters] = await Promise.all([
    api.getProject(projectId, signal),
    api.listVideos(projectId, signal),
    api.listActions(projectId, signal),
    api.listAdapters(signal),
  ]);
  return { project, videos, actions, adapters };
}

export function NewSearchPage({ datasetId }: { datasetId: number }) {
  const data = useApiData((signal) => load(datasetId, signal), [datasetId]);
  const [prompt, setPrompt] = useState("");
  const [name, setName] = useState("");
  const [adapter, setAdapter] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [pending, setPending] = useState<Awaited<ReturnType<typeof prepareSearch>> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  if (data.loading && !data.data) {
    return (
      <div className="page">
        <Loading />
      </div>
    );
  }
  if (!data.data) {
    return (
      <div className="page">
        {data.error ? <ErrorNotice error={data.error} onRetry={data.reload} /> : null}
      </div>
    );
  }

  const { project, videos, actions, adapters } = data.data;
  const ready = videos.filter((video) => video.status === "ready");
  const chosenAdapter = adapter || adapters.default;
  const adapterInfo = adapters.adapters.find((item) => item.name === chosenAdapter) ?? null;
  const trimmed = prompt.trim();
  const autoTitle = promptTitle(trimmed);
  const canSubmit = pending !== null || (trimmed.length >= 3 && ready.length > 0);
  const lockInputs = busy || pending !== null;

  async function run() {
    if (submitting.current || !canSubmit) return;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const launch = pending ?? (await prepareSearch(datasetId, {
        name: uniqueName(name.trim() || autoTitle, actions.map((item) => item.name)),
        description: trimmed,
      }, chosenAdapter));
      setPending(launch);
      await launch.enqueue();
      navigate(`/datasets/${datasetId}/searches/${launch.action.id}`);
    } catch (failure) {
      setError(toApiError(failure));
      setBusy(false);
      submitting.current = false;
    }
  }

  return (
    <div className="page page--narrow">
      <PageHeader
        back={{ href: `#/datasets/${datasetId}`, label: project.name }}
        title="New search"
        subtitle={`Runs on all ${ready.length} ready ${ready.length === 1 ? "video" : "videos"} of ${project.name}.`}
      />
      {ready.length === 0 ? (
        <Notice tone="warning" title="No video to search">
          Upload at least one MP4 video to this dataset first.
        </Notice>
      ) : null}
      <Frame className="form-frame">
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void run();
          }}
        >
          <div className="field">
            <label htmlFor="search-prompt">Describe the action</label>
            <textarea
              id="search-prompt"
              className="input input--prompt"
              value={prompt}
              maxLength={5000}
              disabled={lockInputs}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="e.g. A person is putting on a helmet."
            />
          </div>
          <div className="muted small">
            Describe one action that lasts from a moment to about a minute. A full paragraph that explains what
            counts as the event is fine. Plain language works best.
          </div>
          <div className="stack-sm">
            <span className="muted small">Examples</span>
            <div className="chips-row">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  className="example-chip"
                  disabled={lockInputs}
                  onClick={() => setPrompt(example)}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <label htmlFor="search-name">
              Short name <span className="muted">(optional)</span>
            </label>
            <input
              id="search-name"
              className="input"
              maxLength={190}
              value={name}
              disabled={lockInputs}
              onChange={(event) => setName(event.target.value)}
              placeholder={trimmed ? autoTitle : "Generated from the prompt"}
            />
          </div>
          <div className="field">
            <label htmlFor="search-model">Detection model</label>
            <select
              id="search-model"
              className="input"
              value={chosenAdapter}
              disabled={lockInputs}
              onChange={(event) => setAdapter(event.target.value)}
            >
              {adapters.adapters.map((item) => (
                <option key={item.name} value={item.name} disabled={!item.available}>
                  {item.name} {item.version ? `· ${item.version}` : ""}
                  {item.available ? "" : " (unavailable)"}
                  {item.default ? " (default)" : ""}
                </option>
              ))}
            </select>
          </div>
          {chosenAdapter === "mock" ? (
            <Notice tone="warning" title="Mock model">
              The mock model does not look at the video: its candidates are placeholders for testing the
              workflow.
            </Notice>
          ) : null}
          {adapterInfo?.requires_gpu ? (
            <Notice>This model runs on the worker’s GPU. A search can take a long time on a laptop.</Notice>
          ) : null}
          {error ? (
            <ErrorNotice
              error={error}
              title={pending ? "Search saved, but queueing could not be confirmed" : "The search could not be started"}
            />
          ) : null}
          {pending && error ? (
            <a href={`#/datasets/${datasetId}/searches/${pending.action.id}`}>Open the saved search</a>
          ) : null}
          <div className="form-actions">
            <button
              type="submit"
              className="btn btn-primary btn-lg"
              disabled={!canSubmit || busy}
            >
              {busy ? "Starting…" : pending ? "Retry starting search" : "Run search"}
            </button>
            <a className="btn btn-ghost" href={`#/datasets/${datasetId}`}>
              Cancel
            </a>
            <span className="muted small push-right">Processing can take hours. You can leave and come back.</span>
          </div>
        </form>
      </Frame>
    </div>
  );
}
