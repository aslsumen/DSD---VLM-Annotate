# Release Notes

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
