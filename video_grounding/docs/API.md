# HTTP API integration contract

English | [简体中文](API.zh-CN.md)

For business backends, annotation frontends, and dataset services integrating this engine. This document describes the current `src/video_grounding/server.py` implementation under `/v1`. See [Usage](USAGE.md#http-service-deployment) for deployment.

## Integration conventions

- Default base URL: `http://127.0.0.1:8800`. Send JSON with `Content-Type: application/json`; clip downloads return `video/mp4`.
- Authentication is not built in. The business backend/gateway owns authentication, tenant authorization, rate limits, resource access, and audit records.
- Video paths refer to the **inference server's filesystem**, not the browser or business server. HTTP(S) URLs must be downloadable by the service. Multipart upload, object-storage SDK URIs, and direct binary uploads are unsupported.
- A job contains one video and one or more prompts. There is no API to change its video, prompts, or sampling settings. Configuration comes from the YAML used to start the service; POST does not support per-job overrides.
- Creation has no idempotency key: each POST creates a new job. Persist job_id in the business system. A network timeout does not prove creation failed; do not blindly resubmit. Listing can help reconcile requests, but there is no client_request_id lookup.
- There are no callbacks or event streams. Poll approximately every 3–5 seconds with a configurable long-job timeout. A client timeout does not cancel the server task.
- Persist event references as `(job_id, event_id)`. Event IDs do not include video identity and are not globally unique across videos.

## Recommended sequence

```text
GET health → POST jobs → GET jobs/{id} (poll)
  → GET events → GET clips/{event_id} → POST reviews
  → POST datasets → GET datasets/{id} (poll) → GET manifest / clips
```

Keep these concepts separate in the UI: processing complete, scan coverage complete, Gemini verification complete, and human review complete.

## 1. Health

`GET /v1/health` → 200:

```json
{"status":"ok","model_id":"ZhuYuhan/VideoJev-4B","model_revision":"…","model_loaded":false,"queue_length":0}
```

model_loaded may be false before the first scan; it is not a readiness indicator for synthetic/replay backends either. queue_length excludes the active task and may include dataset tasks. This endpoint does not perform an end-to-end GPU/Gemini readiness check.

## 2. Create a job

`POST /v1/jobs`:

```json
{
  "video": "/data/videos/demo.mp4",
  "prompts": [
    {"query_id":"open_door","text":"A person opens a door"},
    {"query_id":"sit_down","text":"A person sits down"}
  ]
}
```

Single-prompt shorthand: `{"video":"/data/videos/demo.mp4","prompt":"A person opens a door"}`. Its query_id is always `q1`.

- Provide exactly one of prompts or prompt. The prompts list must be nonempty; query IDs must be unique and nonempty; text cannot be whitespace-only.
- A local path must exist and, when media-root is configured, resolve inside it.
- URL reachability is checked during background download. A 202 response does not establish download or inference success. Signed URLs must remain valid through queueing; custom authentication headers are unsupported.

202 response:

```json
{"job_id":"job_0123456789ab","state":"queued"}
```

```bash
curl -sS -X POST http://127.0.0.1:8800/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"video":"/data/videos/demo.mp4","prompt":"A person opens a door"}'
```

## 3. Job status, listing, and retry

`GET /v1/jobs/{job_id}` → 200. Example; progress keys depend on work performed:

```json
{
  "job_id":"job_0123456789ab",
  "state":"refining",
  "video":"/data/videos/demo.mp4",
  "queries":[{"query_id":"q1","text":"A person opens a door"}],
  "progress":{"coarse.succeeded":12,"refine.succeeded":3},
  "error":null,
  "scan_complete":null,
  "n_events":null
}
```

`GET /v1/jobs` returns an **array** of these objects in descending request-file modification time. There is no pagination, filtering, or total-count envelope.

| state | Suggested business mapping | Meaning |
|---|---|---|
| queued | Queued | Request persisted |
| created / probing | Running | Creating, downloading, or probing |
| scanning | Running | Coarse scan |
| refining | Running | Refinement |
| verifying | Running | Gemini verification |
| exporting | Running | Writing JSON and clips |
| completed | Results available | Does not guarantee complete coverage or verification |
| failed / paused | Failed or awaiting recovery | Inspect error, logs, and configuration |

progress is a count of window states, not a percentage or processed-video duration. Refinement can add windows dynamically. scan_complete and n_events come from events.json and are null before output exists. During recovery they can temporarily describe older output; use results after completed.

`POST /v1/jobs/{job_id}/retry` takes no body and returns 202 `{job_id,state:"queued"}`. Only failed/paused jobs that are not already active can be retried; otherwise 409. It reuses the original job directory rather than creating a new job. Source fingerprint, model revision, and configuration checks still apply.

There is no cancellation, deletion, or pause API, and no API to re-verify a completed job. Administrators can use CLI resume as described in Usage.

## 4. Events and clips

`GET /v1/jobs/{job_id}/events` → 200; 409 until the job is completed.

| Top-level field | Type | Meaning |
|---|---|---|
| job_id / video | string | Job ID and inference video path; URL jobs usually expose the downloaded local path here |
| video_duration_sec | number | Source duration |
| backend / model_id / model_revision | string | Grounding backend and model identity |
| scan_complete | boolean | No scan coverage gaps; not Gemini completion |
| queries | array | Each item has query_id, query, warnings, scan_complete |
| events | array | Retained events, including verification failures awaiting human review |
| coverage_gaps | array | Permanently failed windows: query_id, window_id, start_sec, end_sec, reason |
| rejected_events | array, optional | Present when Gemini is enabled; Gemini-negative events, using the same Event shape |

Example Event (illustrative values):

```json
{
  "event_id":"evt_0123456789ab",
  "query_id":"q1",
  "query":"A person opens a door",
  "event_start_sec":12.5,
  "event_end_sec":18.0,
  "clip_start_sec":12.0,
  "clip_end_sec":18.5,
  "complete":"likely",
  "needs_review":false,
  "review_reasons":[],
  "raw_score_max":0.96,
  "alignment_status":"estimated",
  "evidence_window_ids":["window_example"],
  "clip_path":"clips/evt_0123456789ab.mp4",
  "verdict":{"present":true,"p_present":0.91,"model":"gemini-decision-1"}
}
```

Field semantics:

- All `*_sec` fields use **global source-video seconds**, with zero at the first video frame—not exported-clip-local time. In a clip player, the event starts at `event_start_sec - clip_start_sec`.
- event_* are predicted boundaries; clip_* include pre/post-roll, clamped to the source duration. Human adjustments also use source coordinates.
- complete is `likely|unknown`, a heuristic about boundary completeness. needs_review=false is not a human acceptance decision.
- raw_score_max is an uncalibrated VideoJev score, not a final correctness probability. Each query's events are sorted by descending score; the full list is not necessarily chronological.
- alignment_status describes time mapping, commonly `exact|estimated|unknown`. Preserve review_reasons and query warnings; clients should tolerate additional values.
- verdict is null or `{present:boolean,p_present:number,model:string}`. The current cutoff is fixed at 0.5. There are no reason/confidence fields or configurable verdict threshold.
- With verification enabled, failed verification produces verdict=null, needs_review=true, and not_verified in review_reasons. With verification disabled, null does not indicate a failed API call.
- Gemini-negative events appear only in rejected_events and have no newly exported clips. The current review API does not accept their event IDs.
- clip_path is relative to the job directory and may be null. It is not an HTTP URL. Do not expose server-local video paths as browser playback URLs.

`GET /v1/jobs/{job_id}/clips/{event_id}` returns MP4. Supply event_id **without `.mp4`**. Missing files, disabled clip export, or Gemini rejection can result in 404.

**Partial verification failure:** a failed individual call preserves its candidate. A persistent 429 stops remaining verification but allows export, so the job may still complete. Integrations must display verdict/not_verified separately rather than treating completed as proof that all Gemini calls succeeded.

## 5. Human review

`POST /v1/jobs/{job_id}/reviews`:

```json
{
  "reviews": [
    {"event_id":"evt_0123456789ab","accepted":true,"start_sec":12.8,"end_sec":17.6}
  ]
}
```

Only IDs in the completed job's events list are accepted. Either boundary can be omitted; omitted boundaries retain the event's original value. The resulting interval must satisfy `0 <= start < end <= video_duration_sec`. accepted=false records human rejection. The newest review for an event ID replaces the previous review; unmentioned reviews remain.

The 200 response is the review-metrics object itself: `n_candidates, n_reviewed, n_accepted, accept_rate, complete_clip_rate, boundary_adjust_p50, boundary_adjust_p90, per_query`. Some metrics are null when no applicable samples exist. Recall is not included.

`GET /v1/jobs/{job_id}/reviews` → `{"reviews":[...],"metrics":{...}}`. Saving a review does not change events.json or original job clips. Boundary-adjusted clips are created when building a dataset.

## 6. Datasets

`POST /v1/datasets`:

```json
{"name":"door-events-v1","job_ids":["job_0123456789ab"],"include_rejected":false}
```

name and job_ids must be nonempty; every job must be completed. Duplicate job IDs are removed. Returns 202 `{"dataset_id":"ds_0123456789ab","state":"queued"}`.

`GET /v1/datasets/{dataset_id}` → `{dataset_id,state,error,stats}`. State is `queued|running|completed|failed`; stats is usually null before completion. There is no dataset retry endpoint; resolve failures and create a new dataset.

`GET /v1/datasets/{dataset_id}/manifest` returns dataset.json, or 409 before the file exists:

```json
{
  "dataset":"door-events-v1",
  "created_at":"2026-11-12T12:00:00+00:00",
  "model":"ZhuYuhan/VideoJev-4B",
  "model_revision":"…",
  "videos":[{"video":"/data/videos/demo.mp4","job_id":"job_0123456789ab","duration_sec":60.0,"scan_complete":true}],
  "annotations":[{
    "video":"/data/videos/demo.mp4","job_id":"job_0123456789ab","query_id":"q1",
    "prompt":"A person opens a door","start_s":12.8,"end_s":17.6,
    "status":"accepted","engine_event_id":"evt_0123456789ab",
    "clip":"clips/job_0123456789ab_evt_0123456789ab.mp4","adjusted":true,"raw_score_max":0.96
  }],
  "stats":{"n_annotations":1,"n_accepted":1,"n_rejected":0,"n_unreviewed":0}
}
```

- Unreviewed events are omitted. include_rejected only controls inclusion of **human-rejected** events.
- n_rejected counts all human rejections, even with include_rejected=false. It need not equal the number of rejected annotations in the manifest.
- Annotation fields are `start_s/end_s`, still source-video coordinates; their names differ from Event fields.
- Adjusted boundaries trigger source-video recutting with configured pre/post-roll. The original source must remain readable.
- Mixed-model jobs are not rejected; the top-level model comes from the first job. Integrations should group compatible versions.

`GET /v1/datasets/{dataset_id}/clips/{name}` returns MP4. name is the filename from annotations[].clip **without `.mp4`**, e.g. `job_0123456789ab_evt_0123456789ab`.

## Errors and compatibility

| HTTP status | Meaning |
|---|---|
| 200 | Successful query, JSON read, review save, or clip download |
| 202 | Creation/retry accepted; work runs asynchronously |
| 400 | Invalid business input, such as prompt selection, video path, or review interval |
| 404 | Unknown job/dataset ID or missing clip |
| 409 | Job not completed, retry not allowed, or manifest not yet generated |
| 422 | FastAPI/Pydantic request-shape or type validation failure |
| 500 | Unhandled service error; background failures usually appear as failed state and error, not as a 500 on the original POST |

Business errors generally use `{"detail":"explanation"}`. For 422, detail is an array of structured validation errors; do not assume it is always a string.

FastAPI exposes `/docs`, `/redoc`, and `/openapi.json`. Routes currently lack complete typed response models, so OpenAPI primarily documents routes and request shapes. Use this document and the implementation for response semantics. There is no finer-grained compatibility negotiation beyond the API prefix. Pin the service code version in deployments and let clients tolerate additional JSON fields.
