# Release Notes

## Unreleased — `feat/datasets-searches` (2026-11-26)

Development snapshot; not a course release. The dataset/search domain and session authentication are implemented
in the backend alongside the untouched project/action slice. The UI has **not** been cut over yet.

### Added

- **Accounts and access** — `users`, `user_sessions`, `invitations`, global roles (`administrator`,
  `dataset_admin`, `annotator`), email/password sign-in, sign-out, lockout after repeated failures, and
  `VLM_AUTH_REQUIRED` enforcement (migration `d03f1c4ffd30`).
- **Datasets** — `datasets` and `dataset_memberships`; create/list/get, member list and add, and dataset-scoped
  video upload and listing (`POST/GET /api/v1/datasets/{id}/videos`).
- **Searches** — one free-text prompt run over a dataset, fanned out to one job per ready video
  (`searches`, `search_videos`; migrations `e5b9c3d7a2f1`, `c9f0d3a1b2e4`), aggregated status including
  `partial`, dataset-scoped listing with paging and a `status` filter, and search-level cancel / restart.
- **Idempotent search creation** — an optional `Idempotency-Key` header, stored uniquely on
  `searches.idempotency_key` (migration `f1a4b8c2d6e9`); the request is snapshotted in
  `searches.request_scope_json` (migration `b8d2e5a4c9f3`) so a replay is compared against what was asked for
  rather than against live rows, and a different request with the same key returns `409 IDEMPOTENCY_KEY_REUSED`
  with `details.mismatched_fields`.
- **Dataset authorization on the shared legacy routes** — `GET`/`DELETE /videos/{id}`,
  `GET /videos/{id}/stream`, `POST /videos/{id}/jobs`, the `/jobs` family and the `/candidates` family now resolve
  the owning dataset and answer `401` for anonymous callers, `404` for non-members and `403` for members who lack
  the required role, while project-owned rows keep their previous behaviour.

### Changed

- Job and `SearchVideo` writes are committed in **one transaction** on every path (success, failure, cancel,
  retry, reaper), so a crash can no longer leave a `succeeded` job next to a `running` video row; a per-tick
  `reconcile_search_state` sweep repairs rows written by older builds.
- Deleting a video settles the affected searches in the same transaction and removes the stored files only after
  that commit succeeds; `Video.jobs` now declares `passive_deletes=True`, so the database cascade removes the
  video's jobs (and their candidates) instead of nulling the foreign key and stranding a running job.
- A `SQLAlchemyError` inside a job now rolls back and fails the job cleanly instead of leaving it `running` behind
  a poisoned session (`PendingRollbackError`).

### Known limitations

- OpenLABEL JSON export and dataset-scoped exports are not implemented (`dataset_exports` is still project-scoped).
- A dataset membership cannot be revoked (no `DELETE /datasets/{id}/members`) and the `PATCH` route in the target
  contract does not exist.
- Rerunning an existing search for newly uploaded videos is not implemented.
- Password reset and user deactivation are not implemented.
- Protected media playback still needs signed URLs (R-18): a browser `<video>` element cannot send a bearer token.
- The frontend still drives projects and action definitions.

## Unreleased — `backend` branch (2026-11-16)

Development snapshot after v0.2.0-dev; not a course release.

### Added

- **`videojev` adapter** — runs the `video_grounding/` engine (VideoJev-4B) inside the worker
  ([ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md)). Opt-in with `VLM_VLM_ADAPTER=videojev` on a
  GPU worker; `mock` stays the default. Exhaustive: all events kept, zero events is success. Resumes from a per-job
  engine directory on retry; Gemini verify and engine clip cutting are always off.
- **Visual feature cache** for the `videojev` adapter: a later search on the same video skips decode + encode
  (38.6–45.5% less time for two matched video/prompt pairs on the 8 GB laptop). Stored per video under `data/storage/engine/features/`, removed when the
  video or project is deleted ([ARCHITECTURE.md](ARCHITECTURE.md#visual-feature-cache)).
- **Batch job endpoint** `POST /projects/{id}/actions/{action_id}/jobs` (one job per video).
- **Heartbeat lease** — crashed workers' jobs are requeued as `WORKER_LOST` (ADR-0001 amendment); running jobs can
  be cancelled.
- `scripts/smoke_videojev.py` for an end-to-end check on a GPU host.

### Changed

- Engine default `fusion.min_event_score` 0.9 to 0.5.
- Main accuracy benchmark is now `video_grounding/scripts/heldout_bench.py` (33 long YouCook2 and 20 ROAD videos, one
  scan job per video, 2026-11-22). The small composites are an earlier check.
- The benchmark scorer checks the selected video list and reports missing inputs or results before scoring.

### VideoGrounding validation

- On 2026-11-23, the real VideoJev web flow passed on a 52-second public cooking clip with an RTX 3070 Laptop GPU.
  The worker finished one search in about 51 seconds and returned one candidate. In the browser, the reviewer
  played the source and preview, saved the corrected 11–32 s interval and downloaded JSON and ZIP exports.
  Both exports retained the correction, and the ZIP recorded adapter provenance with `mock: false`.

### Known limitations

- Customer footage still needs validation.
- The earlier in-domain Charades-STA reference recorded recall 0.771 and R1@0.5 0.507 at the provisional
  `min_event_score` of 0.5. See the [evaluation report](../video_grounding/docs/EVALUATION.md).
- Held-out long videos (YouCook2 33 videos, ROAD 20, 2026-11-22, verify off): recall 0.86 cooking (95% CI 0.81–0.90)
  and 0.47 driving vs the 0.85 target; CCR 0.78 and 0.82 vs 0.85. Cooking recall meets the target only as a point
  estimate; the other three miss. Absent prompts still give 3.5 (cooking) and 8.4 (driving) candidates per prompt,
  against 5.9 and 9.2 for present prompts, so on driving the model barely tells them apart. Driving finds turns but
  misses lateral moves (0/24), overtakes (3/12) and most stops (35/100). `min_event_score` 0.5 was checked there, not
  re-tuned. The earlier small composites (2026-11-17, recall 0.573 pooled) are superseded.
- Speed reporting uses one video × one prompt per job, with model-loaded state and initial video-cache state
  recorded separately. Actual API/worker measurements and the tested code revisions are in
  [the single-prompt speed report](../video_grounding/docs/EVALUATION.md#speed-kpis).

## v0.2.0-dev — Sprint 2 vertical slice (2026-11-05)

**Not a course release.** Development snapshot for the Requirements & Design presentation and the
2026-11-15 MVP gate. No deployment package yet.

### Added

- **Projects and action definitions** — CRUD, unique action names, natural-language action text.
- **Video pipeline** — streamed upload with extension/content-type/container-signature checks, 2 GiB and
  1 s–4 h limits, ffmpeg probe (duration/resolution/fps), HTTP Range streaming, cascade delete of media.
- **Asynchronous processing** — DB-backed queue, separate worker process (`--once/--loop/--drain`), atomic
  claim, progress, structured error codes, retry with backoff, manual retry, queued cancellation,
  `Idempotency-Key`.
- **Candidates** — normalised model output, clamping with notes, proposal/preview boundary separation,
  real H.264/AAC preview clips with per-candidate error state, review queue filters.
- **Human review** — true/false positive annotations, optional corrected boundaries, notes and reviewer,
  delete-to-unreviewed semantics (no default negatives).
- **Dataset export** — asynchronous ZIP with `manifest.json` (schema 1.0), `labels.csv`, `README.txt` and
  clips; provenance including mock flag and source checksum; guards against empty/unreviewed exports.
- **API** — `/api/v1` with consistent error envelope, OpenAPI at `/api/docs`, optional bearer-token guard.
- **Quality** — 56 pytest tests, ruff-clean, Alembic migration verified on a fresh database, real ffmpeg
  smoke test 26/26 checks.
- **Course artifacts and documents** — calendar, deliverables register, guidelines checklist, requirements,
  design, architecture, API, schema, model evaluation, test plan, risk register, backlogs, burndown, manuals.

### Known limitations

- Candidate intervals come from the **mock adapter**; real VLM inference is not wired (Alpha gate).
- UI is in progress; browser flows not yet automatically tested.
- Only a 2-minute synthetic video has been processed; 10–30 minute real footage is untested.
- Single worker only; PostgreSQL path documented but unverified.
- No retention/purge scheduler, no stale-job reaper.
- Windows-only verification.

### Upgrade notes

Fresh database: run `alembic upgrade head`. There is no previous release to migrate from.

### Verification

See `docs/TEST_PLAN.md` §5 and `docs/evidence/smoke-e2e-20261105-170733.json`.
