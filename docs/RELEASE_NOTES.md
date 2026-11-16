# Release Notes

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
