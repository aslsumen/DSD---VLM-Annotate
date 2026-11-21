# Release Notes

## Unreleased — `backend` branch (2026-11-16)

Development snapshot after v0.2.0-dev; not a course release.

### Added

- **`videojev` adapter** — runs the `video_grounding/` engine (VideoJev-4B) inside the worker
  ([ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md)). Opt-in with `VLM_VLM_ADAPTER=videojev` on a
  GPU worker; `mock` stays the default. Exhaustive: all events kept, zero events is success. Resumes from a per-job
  engine directory on retry; Gemini verify and engine clip cutting are always off.
- **Visual feature cache** for the `videojev` adapter: a later search on the same video skips decode + encode
  (43-53% faster on the 8 GB laptop). Stored per video under `data/storage/engine/features/`, removed when the
  video or project is deleted ([ARCHITECTURE.md](ARCHITECTURE.md#visual-feature-cache)).
- **Batch job endpoint** `POST /projects/{id}/actions/{action_id}/jobs` (one job per video).
- **Heartbeat lease** — crashed workers' jobs are requeued as `WORKER_LOST` (ADR-0001 amendment); running jobs can
  be cancelled.
- `scripts/smoke_videojev.py` for an end-to-end check on a GPU host.

### Changed

- Engine default `fusion.min_event_score` 0.9 to 0.5.

### Known limitations

- Real-model smoke on the RTX 3070 laptop is pending; not validated on product footage.
- Measured on Charades-STA only, below the SPEC targets (recall 0.771 vs 0.85, R1@0.5 0.507 vs 0.70 at
  `min_event_score` 0.5; `video_grounding/docs/EVALUATION.md`).
  *Note 2026-11-16 (later): Charades-STA is in-domain for VideoJev, so these numbers are reference only and
  `min_event_score` 0.5 is provisional. The target check moves to the held-out composite benchmarks (running, results pending).*
- About 0.66× the video duration on an 8 GB laptop with CPU offload (Charades-STA, ~30 s videos; longer
  videos not measured).

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
