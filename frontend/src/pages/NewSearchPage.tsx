/**
 * New search (DS-3, PR-1, PR-3, DET-3; Design Description v1.2, 5.3).
 *
 * One prompt runs on every ready video of the dataset: the client creates the
 * prompt (ActionDefinition) and queues one job per video with the batch endpoint.
 */
import { useState } from "react";

import { ErrorNotice, Frame, Loading, Notice, PageHeader } from "../components/ui";
import { api, newIdempotencyKey, toApiError, type ApiError } from "../lib/api";
import { useApiData } from "../lib/hooks";
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

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const action = await api.createAction(datasetId, {
        name: uniqueName(name.trim() || autoTitle, actions.map((item) => item.name)),
        description: trimmed,
      });
      await api.createActionJobs(datasetId, action.id, { adapter: chosenAdapter }, newIdempotencyKey());
      navigate(`/datasets/${datasetId}/searches/${action.id}`);
    } catch (failure) {
      setError(toApiError(failure));
      setBusy(false);
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
            if (trimmed.length >= 3 && ready.length > 0) void run();
          }}
        >
          <div className="field">
            <label htmlFor="search-prompt">Describe the action</label>
            <textarea
              id="search-prompt"
              className="input input--prompt"
              value={prompt}
              maxLength={5000}
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
          {error ? <ErrorNotice error={error} title="The search could not be started" /> : null}
          <div className="form-actions">
            <button
              type="submit"
              className="btn btn-primary btn-lg"
              disabled={trimmed.length < 3 || ready.length === 0 || busy}
            >
              {busy ? "Starting…" : "Run search"}
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
