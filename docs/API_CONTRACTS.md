# API Contracts — v1.2 target

**Date:** 2026-11-12 (target) · **Base URL:** `/api` (target) · **Auth:** opaque bearer session tokens (implemented; no JWT, no refresh rotation)
**Implemented API today:** `/api/v1`. Since 2026-11-19/26 it carries the session-auth, dataset and search domain **in
addition to** the legacy project/action one, so §9 is a superset rather than "a different domain".

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

> **Note (2026-11-26).** This table is the *target* contract from the design documents. Design Description v1.2
> §4.3 drops `use_case`, so `POST /api/datasets` should take `{name}` (a free-text name) and `PATCH` should not
> accept it. For what is implemented **today** see §9 — including `POST/GET /api/v1/datasets/{id}/videos` and the
> fact that a dataset video lives under `videos.dataset_id` while the legacy project routes stay open.

| Method | Endpoint | Body | Success |
|---|---|---|---|
| POST | `/api/datasets` | `{name}` | 201 `Dataset` |
| GET | `/api/datasets` | `?page=` | 200 paginated (assigned only) |
| GET | `/api/datasets/{id}` | — | 200 `{dataset, videos[], searches[]}` |
| PATCH | `/api/datasets/{id}` | `{name?, assigned_user_ids?}` | 200 (today membership is `POST /datasets/{id}/members`; there is no `PATCH` and no way to revoke a membership yet) |
| DELETE | `/api/datasets/{id}` | — | 204 (cascade videos/searches/candidates/memberships) |
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

- Target paths are `/api/...`; the implemented API is `/api/v1/...`. During migration, `/api/v1` was intended to be
  frozen with the new contract behind `/api/v2` (or under `/api` with a version header).
  **Resolved 2026-11-20:** the team extends `/api/v1` additively instead — the new dataset/auth/search routes are
  new paths, so no frozen endpoint changes. Existing `/api/v1` responses keep their shape; deprecated legacy
  routes will be removed at cutover, not versioned away.
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
| Datasets (Sprint 3) | `POST/GET /api/v1/datasets`, `GET /api/v1/datasets/{id}`, `GET/POST /api/v1/datasets/{id}/members`, `POST/GET /api/v1/datasets/{id}/videos` |
| Searches (Sprint 3) | `POST /api/v1/datasets/{id}/searches` (202, fan-out, optional `Idempotency-Key`), `GET /api/v1/datasets/{id}/searches` (list, filters `status`, `limit`, `offset`), `GET /api/v1/searches/{id}` (aggregated status + per-video results), `POST /api/v1/datasets/{id}/searches/{search_id}/cancel` (200, idempotent once settled), `POST /api/v1/datasets/{id}/searches/{search_id}/retry` (202, re-queues only the failed videos; `409 SEARCH_NOT_RETRYABLE` when none), `GET /api/v1/searches/{id}/candidates` |
| System | `GET /api/v1/health`, `/api/v1/adapters`, `/api/v1/system/media`, `/api/docs` |

**Session authentication (implemented).** The target contract in §2 uses `/api/auth`; the implementation is
mounted at `/api/v1/auth`. Passwords are PBKDF2-HMAC-SHA256 with a per-user salt; only SHA-256 hashes of session
and invitation tokens are stored. Sessions expire after `VLM_AUTH_SESSION_HOURS`; invitations are single-use and
expire after `VLM_AUTH_INVITATION_HOURS`; `VLM_AUTH_MAX_FAILED_LOGINS` failures lock the account for
`VLM_AUTH_LOCKOUT_MINUTES`. Enforcement is behind `VLM_AUTH_REQUIRED` (default `false`, so the current demo
remains open): when enabled, the **auth, dataset and search** routes reject anonymous calls with
`401 UNAUTHENTICATED`.
The existing project/video/job routes still accept `VLM_API_TOKEN` for anonymous legacy work, but since 2026-11-25
they also resolve a session principal and enforce the dataset boundary (see "Dataset authorization on the shared
routes" below); fully migrating them to sessions and signed media URLs is the remaining step (R-18). Refresh
tokens, password reset and pagination are not implemented yet. Dataset
assignment uses `dataset_memberships`. Dataset videos are uploaded through `POST /api/v1/datasets/{id}/videos`;
the legacy `/projects/{id}/videos` route remains for existing projects. **Decided (2026-11-20):** the new dataset,
auth and search routes are added **additively under `/api/v1`** rather than behind `/api/v2`, because they are new
paths that change no frozen endpoint — §8's "decide in Sprint 3" is resolved in favour of extending `/api/v1`.

Behavioural guarantees of that API (timestamps, unreviewed semantics, error envelope, range streaming) are
tested by the pytest suite (162 tests on 2026-11-26) and are the part to carry into the new contract.

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

**Search idempotency.** `POST /api/v1/datasets/{dataset_id}/searches` accepts an optional `Idempotency-Key`
header (≤100 characters). Unlike the batch job route, the key is stored **on the `searches` row itself**
(`searches.idempotency_key`, globally unique) rather than suffixed per video: the search is the unit of
de-duplication, so a repeated request returns `202` with the existing search and its current per-video state
instead of fanning out a second time.

The request itself is recorded too, in `searches.request_scope_json`: a canonical JSON snapshot of `dataset_id`,
`prompt`, `params`, `adapter_name` and the requested `video_ids` (`null` when the caller omitted them). A replay
is compared against that snapshot, never against the live rows, so deleting a video the search was created for
does not make the original request stop matching itself. Equal requests store equal text (`sort_keys`, compact
separators) and the comparison is a set comparison for `video_ids`, so video order and duplicate ids are not a
different request.

| Field | Part of the match | Note |
|---|---|---|
| `dataset_id` | yes | a key is scoped to one dataset |
| `prompt` | yes | whitespace-stripped by the schema first |
| `params` | yes | exact canonical equality of the dict, no tolerance |
| `video_ids` | yes | treated as a set; `null` (= every ready video) is distinct from any explicit subset |
| `adapter_name` | yes | stored resolved, so omitting it equals naming the configured default |
| `title` | no | presentation only |
| resolved video set | no | derived at creation, and later uploads/deletions must not change the request identity |

Reusing a key for a different request is rejected with `409 IDEMPOTENCY_KEY_REUSED` and
`details.mismatched_fields` naming every field that differs. When `video_ids` was omitted the original request
meant "every ready video", so a video uploaded later does not turn a legitimate replay into a conflict. Rows
written before the column existed store `{}`; those fall back to the older dataset + prompt comparison (and the
live video rows) with a logged warning.

**Search cancel and restart.** `POST /api/v1/datasets/{id}/searches/{search_id}/cancel` cancels every `queued` or
`running` video of the search and returns `200` with the settled search; it is idempotent, so a retry after a flaky
connection returns the already-settled search unchanged instead of failing. `POST .../searches/{search_id}/retry`
re-queues **only** the videos whose job failed, leaving the finished ones alone, and returns `202`; it answers
`409 SEARCH_NOT_RETRYABLE` when there is nothing to restart. Both go through `cancel_job` /
`enqueue_candidate_job` so there is still exactly one writer per state, and both require the `dataset_admin` role on
a dataset the caller can access.

**Search status aggregation.** A `Search` mirrors its `SearchVideo` rows: `queued` (all queued), `running` (any
running, or a mix of queued with done/failed), `done` (all done — or no rows left, i.e. every video was deleted),
`failed` (all failed), `partial` (no queued/running left, at least one done and one failed). `finished_at` is
stamped once on entering a terminal state and is not bumped by later re-derivations; `error_message` carries the
first failed video's reason when the search is `failed`. The aggregate is always derived **after** the
`SearchVideo` row is committed, and re-derived until stable, so two workers finishing the last two videos of one
search concurrently cannot both write `running` and strand it.

**Job / SearchVideo / Search write atomicity.** Every write path commits the job row and its `SearchVideo` mirror in
**one transaction** and only then derives the aggregate — success (`_finish` + `done`), failure (`_record_failure` +
`failed`/`queued`), pre-execution failure (`fail_job_now`), retry (`retry_job`), the stale-worker reaper
(`reap_stale_jobs`) and cancel (`cancel_job`). The first child write, which paints the `SearchVideo` `running` in
`execute_job`, is fenced against the job's ownership first: a cancel or reclaim landing between the claim and the
start of execution aborts with `JobInterrupted` and leaves the canceled row alone instead of resurrecting it.
The worker additionally runs `reconcile_search_state` on every tick: it repaints any `SearchVideo` row that disagrees
with its job (job is the source of truth), and re-derives any `Search` still `queued`/`running`/`partial` whose videos
have all settled. It is idempotent and a no-op on a consistent database, so it repairs rows written by older builds or
torn by a hard kill without masking a live write path. Its return value counts both kinds of repair — repainted
`SearchVideo` rows and `Search` aggregates that actually moved — so `0` means the database was consistent.

**Video deletion is a single transaction.** `DELETE /api/v1/videos/{id}` detaches the video from its searches, drops the
`Video` row (which cascades to its `processing_jobs` and `candidates`) and commits, and only then re-derives each affected
`Search`. The settle cannot join the same transaction because it has to see a peer worker's committed row; deriving it
inside would let a crash leave the video alive while its search already reported `done` with zero videos. Stored files
are removed only after the commit, so a rolled-back delete never orphans a surviving row. Because the DDL cascades, the
job history of a deleted video disappears with it — that is intended, and it is why an in-flight job on the video is
abandoned rather than stranded: a statement failure afterwards (`SQLAlchemyError`) rolls the session back, re-reads the
job and, if the row is gone or was taken over, simply returns instead of raising `PendingRollbackError`.

**Candidate list filters.** `GET /api/v1/projects/{id}/candidates` and `GET /api/v1/searches/{id}/candidates`
accept `review_state` (`reviewed` / `unreviewed`) and `verdict` (`true_positive` / `false_positive`) together.
`unreviewed` means "no annotation row", so `review_state=unreviewed&verdict=…` is an empty list, never an error.

**Dataset authorization on the shared routes.** The by-id routes inherited from the single-project API
(`GET/DELETE /api/v1/videos/{id}`, `GET /api/v1/videos/{id}/stream`, `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}`,
`POST /api/v1/jobs/{id}/retry`, `POST /api/v1/jobs/{id}/cancel`, `GET /api/v1/jobs/{id}/candidates`,
`GET/PUT/DELETE /api/v1/candidates/{id}*`) serve both project-owned and dataset-owned rows. Ownership is resolved
from the row (`video.dataset_id`, else the job's video, its `search_videos` row or a candidate it produced) and
checked with the same rules as the dataset routes, inside the handler so that membership is decided before the
role:

| Caller | Dataset-owned row | Project-owned row |
|---|---|---|
| Administrator | allowed | allowed |
| Member with the needed role (`dataset_admin` for video delete, job retry/cancel) | allowed | allowed |
| Member without it (e.g. annotator deleting a video) | `403 FORBIDDEN` with `details.required_roles` | unchanged |
| Signed-in non-member, whatever their global role | `404` (`VIDEO_NOT_FOUND` / `JOB_NOT_FOUND` / `CANDIDATE_NOT_FOUND`) | unchanged |
| Anonymous, authentication enforced | `401 UNAUTHENTICATED` | unchanged (legacy stays open) |

`GET /api/v1/jobs` filters instead of refusing: dataset jobs the caller is not a member of are omitted, legacy
project jobs are always returned. A search job whose video was deleted has neither `project_id` nor `video_id`;
it is visible to administrators only and `404` to everyone else. Annotating needs membership, not a write role —
it is the annotator's job. Note that lazily created annotations (`PUT /candidates/{id}/annotation`) still take
`reviewer` from the payload; the session identity is not yet written there.

**Exhaustive adapters.** An adapter that reports `exhaustive` (currently `videojev`) returns every event it
finds: the `max_candidates_per_job` cap does not apply, candidates are ranked by score descending, and zero
events is a successful job with an empty candidate list (the action does not occur in that video). Other
adapters keep the cap (earliest 12 by start time) and fail a job that yields no candidates.

Behavioural guarantees of that API (timestamps, unreviewed semantics, error envelope, range streaming) are
tested by the pytest suite (162 tests on 2026-11-26) and are the part to carry into the new contract.
