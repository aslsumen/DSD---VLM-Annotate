# As-built baseline — 2026-11-05 (implemented prototype)

**What this file is.** A consolidated record of the working prototype as it existed on 2026-11-05, before the
repository documents were aligned to the team's Requirements/Design v1.1 and the customer's latest email
(CE-2). It preserves the implementation detail that the v1.2 target documents intentionally condensed.

**Status:** historical / as-built. **Superseded for target requirements and design by**
[../REQUIREMENTS.md](../REQUIREMENTS.md) and [../DESIGN_DESCRIPTION.md](../DESIGN_DESCRIPTION.md). **Still
authoritative for** what the code in `backend/` and `frontend/` actually does today.

> **Why it exists.** On 2026-11-12 the requirements and design were rewritten to match the team's v1.1
> documents and the customer's answers (global roles, invitations, datasets, searches, OpenLABEL JSON). That
> rewrote the v1.0 prose. No team-authored content was lost (the folder had no documentation before
> 2026-11-05), but the as-built detail below is worth keeping for migration and traceability.

---

## 1. Implemented API (frozen reference)

**Base:** `/api/v1` · **Auth:** optional `Authorization: Bearer $VLM_API_TOKEN` (middleware; `/health` public)
**Docs:** `/api/docs` · **Timestamps:** seconds relative to the source video, half-open `[start, end)`.

### 1.1 Endpoints

| Method | Path | Body | Success |
|---|---|---|---|
| GET | `/health` | — | 200 `{status, app, version, environment, database, adapter}` |
| GET | `/adapters` | — | 200 `{adapters[], default}` |
| GET | `/system/media` | — | 200 `{ffmpeg, version, available}` |
| POST | `/projects` | `{name, description?}` | 201 project |
| GET | `/projects` | `?limit&offset` | 200 list |
| GET/PATCH/DELETE | `/projects/{id}` | `{name?, description?}` | 200 / 204 |
| GET | `/projects/{id}/stats` | — | 200 counters |
| POST/GET | `/projects/{id}/actions` | `{name, description}` | 201 / 200 |
| PATCH/DELETE | `/actions/{id}` | `{name?, description?}` | 200 / 204 |
| POST | `/projects/{id}/videos` | multipart `file` | 201 video |
| GET | `/projects/{id}/videos` | — | 200 list |
| GET/DELETE | `/videos/{id}` | — | 200 / 204 |
| GET | `/videos/{id}/stream` | `Range` | 200/206 |
| POST | `/videos/{id}/jobs` | `{action_id, adapter?, params?}` + optional `Idempotency-Key` | **202** job |
| GET | `/jobs` | `?project_id&video_id&status&limit` | 200 list |
| GET | `/jobs/{id}` | — | 200 job |
| POST | `/jobs/{id}/retry` | — | 202 job |
| POST | `/jobs/{id}/cancel` | — | 200 job |
| GET | `/jobs/{id}/candidates` | — | 200 candidates |
| GET | `/projects/{id}/candidates` | `?video_id&action_id&review_state&verdict&limit` | 200 list |
| GET | `/candidates/{id}` | — | 200 candidate |
| PUT | `/candidates/{id}/annotation` | `{verdict, corrected_start_seconds?, corrected_end_seconds?, note?, reviewer?}` | 200 candidate |
| DELETE | `/candidates/{id}/annotation` | — | 204 |
| GET | `/candidates/{id}/clip` | `Range` | 200/206 mp4 |
| POST | `/projects/{id}/exports` | `{include_unreviewed?}` | **202** `{export, job}` |
| GET | `/projects/{id}/exports` | — | 200 list |
| GET/DELETE | `/exports/{id}` | — | 200 / 204 |
| GET | `/exports/{id}/download` | — | 200 zip |

### 1.2 Timestamp contract

- Unit: float seconds, source-video relative; half-open interval; rounded to 3 decimals.
- Three families, never overwritten: **proposal** (`candidate.start/end_seconds`),
  **preview** (`preview_start/end_seconds`), **correction** (`annotation.corrected_*`).
- Effective label = corrected if present, else proposal. Preview is never a label.
- Validation: `0 ≤ start < end ≤ duration`; invalid model output is clamped and the fact recorded in
  `model_notes`.

### 1.3 Job state machine

```text
[none] --enqueue--> queued --claim--> running --success--> succeeded
                      |                  |
                 cancel|                  | retryable error (attempts < max) -> queued (backoff)
                      v                  v
                   canceled            failed --manual retry--> queued
```

- `progress` 0..1; `attempts`, `max_attempts`, `error_code`, `error_message`, `adapter_name/version` persisted.
- Claim is an atomic conditional `UPDATE ... WHERE status='queued'`; `rowcount=0` means another worker won.
- Retry deletes the job's previous candidates before re-inserting (unique `job_id, rank`).

### 1.4 Error envelope and codes

```json
{"code":"VIDEO_DURATION_OUT_OF_RANGE","message":"...","details":{"min_seconds":1.0,"max_seconds":14400.0}}
```

Stable codes: `VALIDATION_ERROR`, `UNAUTHENTICATED`, `PROJECT_NOT_FOUND`, `VIDEO_NOT_FOUND`, `ACTION_NOT_FOUND`,
`JOB_NOT_FOUND`, `CANDIDATE_NOT_FOUND`, `EXPORT_NOT_FOUND`, `FILE_NOT_FOUND`, `CLIP_NOT_AVAILABLE`,
`ACTION_NAME_TAKEN`, `PROJECT_MISMATCH`, `VIDEO_NOT_READY`, `ADAPTER_UNAVAILABLE`, `EMPTY_PROJECT`,
`NO_REVIEWED_CANDIDATES`, `JOB_NOT_RETRYABLE`, `JOB_NOT_CANCELABLE`, `EXPORT_NOT_READY`, `EXPORT_RUNNING`,
`UPLOAD_TOO_LARGE`, `UNSUPPORTED_VIDEO_EXTENSION`, `UNSUPPORTED_CONTENT_TYPE`, `UNRECOGNISED_CONTAINER`,
`CONTAINER_MISMATCH`, `INVALID_RANGE`, `RANGE_NOT_SATISFIABLE`, `VIDEO_DURATION_OUT_OF_RANGE`,
`MEDIA_PROBE_FAILED`, `INVALID_CORRECTED_INTERVAL`, `UNKNOWN_ADAPTER`, `JOB_FAILED`.

## 2. Implemented database schema (SQLite, Alembic `0001_initial_schema`)

| Table | Columns (key) | Constraints |
|---|---|---|
| `projects` | id, name, description, created_at, updated_at | PK |
| `action_definitions` | id, project_id, name, description, timestamps | FK project CASCADE; unique (project_id, name) |
| `videos` | id, project_id, original_filename, storage_key, content_type, size_bytes, checksum_sha256, duration_seconds, width, height, fps, status, error_message, created_at | FK project CASCADE; storage_key unique; size ≥ 0 |
| `processing_jobs` | id, kind, status, project_id, video_id, action_id, export_id, progress, attempts, max_attempts, available_at, idempotency_key, error_code/message, adapter_name/version, params_json, timestamps | FKs; idempotency unique; index (status, available_at) |
| `candidates` | id, job_id, video_id, action_id, start/end_seconds, preview_start/end_seconds, rank, score, model_notes, clip_storage_key, clip_status, clip_error, created_at | FK job CASCADE; unique (job_id, rank); checks start ≥ 0, end > start |
| `annotations` | id, candidate_id, verdict, corrected_start/end_seconds, note, reviewer, timestamps | FK candidate CASCADE; candidate unique; verdict in (true_positive, false_positive); correction checks |
| `dataset_exports` | id, project_id, format, status, include_unreviewed, storage_key, size_bytes, item_count, error_message, timestamps | FK project CASCADE |

Invariants enforced in services/tests: interval bounds, preview inside the video and ≤ 90 s, one label per
candidate, unreviewed = no annotation row, export only reviewed unless explicitly requested.

## 3. Implemented architecture and flows

- **API** (FastAPI) + **worker** (separate process, `python -m app.worker --loop`) + **SQLite** + **local
  storage** behind a `StorageBackend` protocol. No Redis/Celery/PostgreSQL/object storage yet.
- Upload: extension + MIME + container signature + size + duration + ffprobe; streamed to a generated key with
  SHA-256; failures delete the stored file.
- Clip extraction: ffmpeg (bundled by `imageio-ffmpeg`), H.264/AAC, `+faststart`, per-candidate failure state.
- Export: async job building a ZIP with `manifest.json`, `labels.csv`, `README.txt`, `clips/`.
- Review UI: source player + clip player, J/F shortcuts, filters, unreviewed counter, corrections, auto-advance,
  MOCK banner.
- Failure handling: retryable model/media/storage errors requeue with backoff; adapter-unavailable fails
  immediately; partial clip failures keep candidates reviewable (`CLIP_EXTRACTION_PARTIAL`).

## 4. Original requirements map (v1.0, obsolete scope)

These IDs are kept only for traceability to the v1.0 test suite; the current requirements use the team's
DS/PR/DET/REV/EXP/USR IDs.

| Old ID | Requirement | Verified by |
|---|---|---|
| FR-01 | Project CRUD | `test_api_projects.py` |
| FR-02 | Actions with NL description | `test_api_projects.py` |
| FR-03 | Upload with format validation | `test_api_videos.py` |
| FR-04 | Size/duration limits | `test_api_videos.py` |
| FR-05 | Server-side probe | smoke + `test_api_videos.py` |
| FR-06 | Range streaming | `test_api_videos.py` |
| FR-07 | Cascade delete + files | `test_api_videos.py` |
| FR-08 | Async enqueue (202) | `test_flow.py` |
| FR-09 | Job state/progress/errors | `test_worker.py` |
| FR-10 | Retry + idempotent re-run | `test_worker.py` |
| FR-11 | Manual retry / cancel | `test_worker.py` |
| FR-12 | Idempotency-Key | `test_flow.py` |
| FR-13 | Atomic claim, single worker | `test_worker.py` |
| FR-14 | Candidate intervals with bounds | `test_validation.py`, `test_flow.py` |
| FR-15 | Playable preview clips | smoke 26/26 |
| FR-16 | Proposal/preview/correction separation | `test_validation.py`, export tests |
| FR-17 | True/false-positive labels | `test_flow.py` |
| FR-18 | Unreviewed distinct from negative | `test_flow.py` |
| FR-19 | Keyboard review UX | UI build/report |
| FR-20 | Corrected boundaries with validation | `test_flow.py` |
| FR-21 | Adapter provenance + mock label | `test_flow.py` |
| FR-22 | Async export | `test_flow.py` |
| FR-23 | Export manifest/CSV/clips/provenance | `test_flow.py`, smoke |
| FR-24 | Refuse export with nothing reviewed | `test_flow.py` |
| FR-25 | Refuse empty project | `test_flow.py` |
| FR-26 | Download + item count | `test_flow.py` |
| FR-27 | Responsive UI | UI build + 375 px check |
| FR-28 | Optional bearer token | `test_security.py` |

Non-functional v1.0: NFR-01 async isolation · NFR-02 size/duration · NFR-03 timestamp correctness ·
NFR-04 checksums/atomic writes · NFR-05 untrusted input · NFR-06 privacy/retention · NFR-07 observability ·
NFR-08 reproducibility · NFR-09 portability · NFR-10 maintainability · NFR-11 testability · NFR-12
accessibility · NFR-13 error clarity · NFR-14 model neutrality.

## 5. What changed on 2026-11-12 and why

| Change | Reason |
|---|---|
| Requirements rewritten to team IDs (DS/PR/DET/REV/EXP/USR) | The team's v1.1 PDF is the submission; repository IDs had to match |
| Roles, invitations, datasets, searches, JSON export added | Customer CE-2 answers + Requirements v1.1 |
| 5-min MVP / 30-min Should | Customer confirmed video spec from the kick-off |
| Summaries/tags marked outside MVP | Customer CE-1/CE-2 priority |
| Detection engine target (VideoJev-4B/Gemini) added | Design v1.1 and Gemini key |
| Model evaluation rewritten | Gemini access, dataset memo, 12 GB GPU offer |
| API/DB/architecture docs reframed as target + current | The implemented slice no longer matches the MVP scope |

## 6. Verification state at 2026-11-12

- 56 backend tests, 21 UI tests, ruff clean, migration verified, real-ffmpeg smoke 26/26.
- No application code was changed on 2026-11-12; only documentation.
- The prototype is runnable with the commands in `docs/INSTALLATION_MANUAL.md`.
