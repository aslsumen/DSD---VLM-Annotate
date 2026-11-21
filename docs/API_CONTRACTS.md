# API Contracts — v1.2 target

**Date:** 2026-11-12 · **Base URL:** `/api` (target) · **Auth:** session/JWT (decision pending)
**Implemented API today:** `/api/v1` with a different domain (see §9). The target below is what the MVP needs.

> **As-built detail for the implemented prototype:** [docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md](as-built/IMPLEMENTED_BASELINE_2026-11-05.md).

## 1. Conventions

- JSON bodies; UTF-8; ISO-8601 UTC timestamps.
- **Time unit:** seconds, relative to the source video, half-open `[start, end)`; UI displays `mm:ss`.
- **Long operations return `202`** plus an id; clients poll the status endpoint.
- **Pagination envelope** for lists:
  ```json
  {"items": [...], "total_items": 100, "current_page": 1, "page_size": 20}
  ```
- **Error envelope:** `{"code": "SNAKE_CASE", "message": "human readable", "details": {...}}`
  with stable codes (`UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `CONFLICT`,
  `RATE_LIMITED`, `INTERNAL_ERROR`).
- **Authorization:** every route checks the global role and dataset scope. Annotators can only read assigned
  datasets and review their candidates; Dataset Administrators additionally manage their own datasets, upload,
  define prompts, launch searches, invite users within their scope and export; Administrators can do everything.
- **Media:** never public. The API issues short-lived signed URLs for playback/download.

## 2. Authentication and accounts

| Method | Endpoint | Body | Success | Notes |
|---|---|---|---|---|
| POST | `/api/auth/login` | `{email, password}` | 200 + session/token | Neutral error for unknown email or wrong password; 5 failures/15 min → 15 min block (NFR-14) |
| POST | `/api/auth/logout` | — | 204 | Revokes the server-side session (NFR-12) |
| POST | `/api/auth/refresh` | refresh token/cookie | 200 | Rotation; only while active (NFR-13) |
| POST | `/api/auth/password-reset` | `{email}` | 202 | Always 202 (does not reveal account existence) |
| POST | `/api/auth/password-reset/confirm` | `{token, password}` | 204 | Single-use token |
| GET | `/api/me` | — | 200 `{id, email, full_name, role, organization, datasets[]}` | Used by route guards |
| POST | `/api/users/invitations` | `{email, full_name, role, organization?, dataset_ids?}` | 201 `{id, expires_at}` | Admin, or Dataset Admin for datasets they manage (CE-2) |
| POST | `/api/users/invitations/accept` | `{token, password, full_name?}` | 201 + session | Single-use, 48 h (NFR-11) |
| GET | `/api/users` | `?role=&page=` | 200 paginated | Admin sees all; Dataset Admin sees annotators |
| PATCH | `/api/users/{id}` | `{role?, status?, dataset_ids?}` | 200 | Role change, deactivation (USR-7), dataset assignment |

## 3. Datasets and videos

| Method | Endpoint | Body | Success |
|---|---|---|---|
| POST | `/api/datasets` | `{name, use_case}` | 201 `Dataset` |
| GET | `/api/datasets` | `?page=` | 200 paginated (assigned only) |
| GET | `/api/datasets/{id}` | — | 200 `{dataset, videos[], searches[]}` |
| PATCH | `/api/datasets/{id}` | `{name?, use_case?, assigned_user_ids?}` | 200 |
| DELETE | `/api/datasets/{id}` | — | 204 (cascade videos/searches/candidates/assignments) |
| POST | `/api/datasets/{id}/videos` | multipart `file` (MP4, 720p/1080p, ≤5 min MVP / ≤30 min Should) | 201 `Video(status=ready)` after probe |
| GET | `/api/datasets/{id}/videos` | `?page=` | 200 paginated |
| GET | `/api/videos/{id}/playback-url` | — | 200 `{url, expires_at}` signed, short-lived |
| GET | `/api/videos/{id}/stream` | `Range` | 200/206 (only if signed URL mode not used) |

## 4. Searches and candidates

| Method | Endpoint | Body | Success |
|---|---|---|---|
| POST | `/api/datasets/{id}/searches` | `{prompt, model_config_id?}` | **202** `{search_id}` |
| GET | `/api/searches/{id}` | — | 200 `{id, status, progress, video_results[], error}` |
| GET | `/api/datasets/{id}/searches` | `?page=` | 200 paginated (history/reuse) |
| GET | `/api/searches/{id}/candidates` | `?video_id=&review_status=&min_confidence=&page=` | 200 paginated, all videos in one list |
| GET | `/api/candidates/{id}` | — | 200 `Candidate` |
| PATCH | `/api/candidates/{id}` | `{start_s?, end_s?, review_status, note?}` | 200 `Candidate` |

**Search status:** `queued | running | done | failed`.
**Candidate:** `{id, search_id, video_id, original_start_s, original_end_s, start_s, end_s, confidence,
preview_url, review_status, reviewer_email, reviewed_at, needs_review, review_reasons[]}`.
**Review status:** `pending | accepted | rejected`. Unreviewed (`pending`) is never exported as a negative.

Validation: `0 ≤ start_s < end_s ≤ video.duration_s`; adjusted boundaries stored in `start_s`/`end_s`,
raw model output remains in `original_*`.

## 5. Export

| Method | Endpoint | Body | Success |
|---|---|---|---|
| POST | `/api/exports` | `{dataset_id, search_id?, include_rejected?}` | **202** `{export_id}` |
| GET | `/api/exports/{id}` | — | 200 `{status, item_count, size_bytes, download_url?}` |
| GET | `/api/exports` | `?dataset_id=&page=` | 200 paginated history |
| DELETE | `/api/exports/{id}` | — | 204 (not while running) |

Status: `queued | running | done | failed`. The artifact is the OpenLABEL-based JSON proposed in
`DESIGN_DESCRIPTION.md` §9 (pending customer confirmation), optionally with clips.

## 6. Engine service (internal, GPU host) — not built

> **Status 2026-11-16:** this HTTP service is not built and is no longer planned. The engine (`video_grounding/`) is a
> library the worker calls in-process through the `videojev` adapter ([ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md));
> its HTTP server was removed. The table is the earlier target design only.

Not called by the browser. Worker → engine:

| Method | Endpoint | Body/Result |
|---|---|---|
| POST | `/v1/jobs` | `{video, prompts:[{query_id,text}]}` → 202 `{job_id}` |
| GET | `/v1/jobs/{id}` | `{state, progress, error, n_events}` |
| GET | `/v1/jobs/{id}/events` | event list with times, flags, scores |
| GET | `/v1/jobs/{id}/clips/{event_id}` | MP4 preview |
| POST | `/v1/jobs/{id}/reviews` | review decisions for KPI computation |
| POST | `/v1/jobs/{id}/retry` | resume a failed job |
| GET | `/v1/health` | `{model_id, model_loaded, queue_length}` |

## 7. Health and operations

`GET /api/health` → `{status, version, database, engine, queue}` (liveness/readiness for NFR-10).

## 8. Compatibility and versioning

- Target paths are `/api/...`; the implemented API is `/api/v1/...`. During migration, `/api/v1` is frozen and
  the new contract is added behind `/api/v2` or directly under `/api` with a version header. Decide in Sprint 3.
- Additive fields are allowed; enum changes require a version bump; OpenAPI is generated from Pydantic models.

## 9. Implemented API today (frozen reference)

| Area | Endpoints |
|---|---|
| Projects/actions | `POST/GET /api/v1/projects`, `GET/PATCH/DELETE /api/v1/projects/{id}` (delete also removes its videos' `engine/features/video-<id>` and its jobs' `engine/job-<id>` directories), `POST/GET /api/v1/projects/{id}/actions`, `PATCH/DELETE /api/v1/actions/{id}` (delete removes the action with its candidate jobs, candidates, annotations, clips and engine work directories, but not the video's feature cache; a worker still running one of those jobs drops its result at the next lease fence) |
| Videos | `POST/GET /api/v1/projects/{id}/videos`, `GET/DELETE /api/v1/videos/{id}` (delete also removes `engine/features/video-<id>` and the `engine/job-<id>` directories of its jobs), `GET /api/v1/videos/{id}/stream` |
| Jobs | `POST /api/v1/videos/{id}/jobs`, `POST /api/v1/projects/{id}/actions/{action_id}/jobs` (batch), `GET /api/v1/jobs` (filters `project_id`, `video_id`, `action_id`, `status`, `limit`), `GET /api/v1/jobs/{id}`, retry (failed jobs), cancel (queued or running jobs; `409 JOB_NOT_CANCELABLE` otherwise), `GET /api/v1/jobs/{id}/candidates` |
| Review | `GET /api/v1/projects/{id}/candidates`, `GET /api/v1/candidates/{id}`, `PUT/DELETE /api/v1/candidates/{id}/annotation`, `GET /api/v1/candidates/{id}/clip` |
| Export | `POST/GET /api/v1/projects/{id}/exports`, `GET/DELETE /api/v1/exports/{id}`, `GET /api/v1/exports/{id}/download` |
| Auth (Sprint 3) | `POST /api/v1/auth/bootstrap` (`X-Bootstrap-Token`, first admin only), `POST /api/v1/auth/login`, `POST /api/v1/auth/accept-invitation`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/invitations`, `GET /api/v1/auth/users` |
| Datasets (Sprint 3) | `POST/GET /api/v1/datasets`, `GET /api/v1/datasets/{id}`, `GET/POST /api/v1/datasets/{id}/members` |
| System | `GET /api/v1/health`, `/api/v1/adapters`, `/api/v1/system/media`, `/api/docs` |

**Session authentication (implemented).** The target contract in §2 uses `/api/auth`; the implementation is
mounted at `/api/v1/auth`. Passwords are PBKDF2-HMAC-SHA256 with a per-user salt; only SHA-256 hashes of session
and invitation tokens are stored. Sessions expire after `VLM_AUTH_SESSION_HOURS`; invitations are single-use and
expire after `VLM_AUTH_INVITATION_HOURS`; `VLM_AUTH_MAX_FAILED_LOGINS` failures lock the account for
`VLM_AUTH_LOCKOUT_MINUTES`. Enforcement is behind `VLM_AUTH_REQUIRED` (default `false`, so the current demo
remains open): when enabled, the auth and dataset routes reject anonymous calls with `401 UNAUTHENTICATED`.
The existing project/video/job routes still use `VLM_API_TOKEN`; migrating them to sessions and signed media URLs
is the next step (R-18). Refresh tokens, password reset and pagination are not implemented yet. Dataset
assignment uses `dataset_memberships`; videos still belong to a project until the dataset migration.

Behavioural guarantees of that API (timestamps, unreviewed semantics, error envelope, range streaming) are
tested by the pytest suite (90 tests on 2026-11-19) and are the part to carry into the new contract.

**Job cancel and lost workers.** `POST /api/v1/jobs/{id}/cancel` works on `queued` and `running` jobs; a running
worker stops at its next progress tick and its result is discarded. A running job whose worker stops
heart-beating is requeued with `error_code=WORKER_LOST` (status `queued`, attempts kept), or set to `failed`
with `error_code=WORKER_LOST` once `max_attempts` is exhausted.

**Batch jobs.** `POST /api/v1/projects/{project_id}/actions/{action_id}/jobs` with body
`{"video_ids": [1, 2] | null, "adapter": "videojev" | null, "params": {}}` queues one job per video and returns
`202` with a list of `JobOut`. `video_ids` omitted/null means every `ready` video in the project; duplicates are
ignored. Errors: `404` unknown project/action/video, `409 PROJECT_MISMATCH` (action or video in another
project), `409 VIDEO_NOT_READY` (a listed video is not ready). An optional `Idempotency-Key` header is applied
per video as `<key>:<video_id>`, so repeating the request returns the same jobs. Keys longer than 100
characters are rejected with `422` on both job endpoints (the column is 128 wide).

**Exhaustive adapters.** An adapter that reports `exhaustive` (currently `videojev`) returns every event it
finds: the `max_candidates_per_job` cap does not apply, candidates are ranked by score descending, and zero
events is a successful job with an empty candidate list (the action does not occur in that video). Other
adapters keep the cap (earliest 12 by start time) and fail a job that yields no candidates.

Behavioural guarantees of that API (timestamps, unreviewed semantics, error envelope, range streaming) are
tested by the pytest suite (90 tests on 2026-11-19) and are the part to carry into the new contract.
