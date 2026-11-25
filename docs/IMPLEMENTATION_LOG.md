# Implementation Log

Chronological record of what was actually built, changed and measured. Newest last.

## 2026-11-25 — Review-filter combination and concurrent search completion

**Goal:** two defects reported in PR review. (a) Filtering the candidate lists by `review_state` **and**
`verdict` together returned `500`: each condition added its own join of `annotations`, so the compiled SQL
selected the table twice and every column reference became ambiguous. (b) Two workers finishing the last two
videos of the same search at the same moment could leave that search `running` for ever: each derived the
aggregate from a transaction that did not include its peer's committed `SearchVideo` row, both wrote
`running`, and nothing derived the search again.

**Code**

- `app/api/searches.py` (`list_search_candidates`) and `app/api/candidates.py` (`list_project_candidates`):
  `annotations` is now joined **at most once**. `review_state=unreviewed` keeps the outer join
  (`Annotation.id IS NULL`); `reviewed` *or* a standalone `verdict` filter adds the single inner join; the
  verdict predicate is a plain `.where()` on that same alias. `review_state=unreviewed&verdict=…` is still an
  empty result, not an error.
- `app/services/pipeline.py`: new `_settle_search_status(session, search_id, *, max_rounds=3)` **commits the
  row write first and only then derives** the aggregate, re-deriving with `session.expire_all()` until the
  derived status stops changing. Whoever commits last therefore always reads the rows its peer already
  committed and settles on the terminal state.
- `app/services/pipeline.py`: `_sync_search_video_status` routes through `_settle_search_status` when
  `commit=True`; with `commit=False` (reaper, cancel — the caller owns the transaction and must keep the
  multi-row update atomic) it keeps deriving in that same transaction. `refresh_searches_for_video` settles
  each affected search, so a worker finishing another video of the same search is not missed.
- `tests/test_review_filters.py` (new, 3 tests): each filter alone, the previously failing combination on both
  the project and the search route, the `unreviewed + verdict` empty case, and verdict-only.
- `tests/test_searches.py`: `test_concurrent_completion_settles_the_search` spies on `_recompute_search_status`
  and, at each derivation, reads the rows from a **separate** session to assert the worker's own row is already
  committed and visible; it then finishes the second video and asserts the search reaches `done`.
- **No migration:** pure Python; no column, table or enum changed.

**Trade-off to note:** `refresh_searches_for_video` now commits internally, so in `DELETE /videos/{id}` the
`SearchVideo` rows are committed just before the `Video` row is deleted. If that final delete failed, the
affected searches would already have settled as though the video were gone. Accepted because the delete is a
single row with no blocking FK.

**Verification (actual):** `pytest -q` run by the user on Windows (2026-11-25) — **all tests pass**. The suite
is now **125 tests**: the prior 121, plus 3 in `test_review_filters.py` and 1 concurrency test in
`test_searches.py`.

## 2026-11-24/25 — Stuck Search statuses: cancel, requeue, retry and video deletion

**Goal:** a `Search` must never stay `queued`/`running` forever. Before this change, three paths broke the
`Search` ↔ `SearchVideo` invariant: `cancel_job` never touched the `SearchVideo` row it belonged to,
`reap_stale_jobs` re-queued or failed the job but left the row `running`, and deleting a video left
`SearchVideo` rows pointing at a row that no longer existed (the `videos` list kept a ghost entry and the
parent `Search` never settled). The same held for `retry_job`.

**Code**

- `app/services/pipeline.py`: new `_sync_search_video_status(session, job, status, error_message=None,
  *, commit=True)` is now the single choke point — it resolves the `SearchVideo` by `job_id`, writes
  status/message, and recomputes the parent. The old `_sync_search_video` was deleted; every caller
  (`execute_job`, `fail_job_now`, `cancel_job`, `reap_stale_jobs`, `retry_job`) goes through the new helper.
- `app/services/pipeline.py`: `_recompute_search_status` now settles an empty row set as `done` with
  `finished_at` instead of returning early (deleting the last video must not freeze the search), and it fills
  `Search.error_message` from the first failed video when the search is `failed` (clearing it otherwise).
- `app/services/pipeline.py`: new public `refresh_searches_for_video(session, video_id)` drops the
  `SearchVideo` rows of a video and re-derives each affected search; exported in `__all__`.
- `app/services/pipeline.py`: `reap_stale_jobs` and `cancel_job` paint the ORM `job` object in memory before
  syncing, because the preceding bulk `update()` uses `synchronize_session=False` and `expire_on_commit=False`
  would otherwise make the helper read a stale status and take the wrong branch.
- `app/api/videos.py`: `delete_video` calls `refresh_searches_for_video` **before** `session.delete(video)`.
- **No migration:** the fix is pure Python. A canceled job is represented as `SearchVideoStatus.failed` with
  `error_message = "Job canceled"` — adding a `canceled` member to the search enums was rejected because it
  contradicts the documented state machine (`DESIGN_DESCRIPTION.md:121`) and would need model, schema, API and
  SQLite constraint work for no behavioural gain.
- `tests/test_searches.py`: 7 new regression tests (section 6), each starting from the state a worker leaves
  mid-run rather than from `queued`, so they fail against the old code: cancel one video → `running` with
  `failed_videos == 1` and `"Job canceled"` kept; cancel all → `failed` with the reason on the search; reaper
  requeue → `SearchVideo` back to `queued` and the job claimable again; reaper exhausted → `failed` with
  `"attempts exhausted"`; retry → `SearchVideo` and search back to `queued` with the error cleared; delete a
  running video → search re-derived and no orphan row; delete the last video → `done` instead of stuck.

**Verification (actual):** `pytest -q` → **121 passed** (2026-11-25; 7 new tests on top of the prior 114) and
`ruff check --no-cache backend\app backend\tests` clean, both run by the user on Windows.

## 2026-11-24 — Dataset search listing + `Idempotency-Key` on search creation

**Goal:** give the frontend a way to restore the search list on page reload (`GET /datasets/{id}/searches`)
and make search creation replay-safe so a double click cannot fan out a second search.

**Code**

- `app/models.py`: `Search.idempotency_key` (`String(100)`, nullable) + `UniqueConstraint` named
  `uq_search_idempotency_key`. The key lives on the **search**, not on the per-video jobs: the search is the
  unit of de-duplication, and reusing suffixed job keys would create a second `Search` whose `SearchVideo` rows
  point at already-finished jobs and would stay `queued` forever.
- Migration `f1a4b8c2d6e9_search_idempotency_key.py` (down_revision `c9f0d3a1b2e4`): batch
  `add_column` + `create_unique_constraint`; `downgrade()` reverses both.
- `app/api/searches.py`:
  - new `GET /datasets/{dataset_id}/searches` → `list[SearchOut]`; `get_current_principal` + `_require_access`
    (admin sees all, member sees own datasets, non-member gets `404 DATASET_NOT_FOUND`); filters `status`
    (alias for the `SearchStatus` enum), `limit` (default 100, 1…500) and `offset` (default 0); newest first
    (`created_at desc, id desc`). Counts come from a single `_aggregate_many` query (`SearchVideo.search_id IN
    (...)`) so the list does not issue one query per row.
  - `create_search` now accepts an optional `Idempotency-Key` header (≤100 chars). Lookup by key before
    creating; a replay returns `202` with the existing search and its **current** aggregated state. A replay
    with a different `prompt`/`dataset_id`/`video_ids` scope raises `409 IDEMPOTENCY_KEY_REUSED`. The
    `flush()` is wrapped in `try/except IntegrityError` → rollback + re-select + replay, so two concurrent
    requests with the same key cannot both create a search. A blank header is normalised to `None`.
  - helpers `_aggregate_many`, `_with_counts`, `_detail`, `_video_ids_for`, `_replay_matches`,
    `_replay_or_conflict`; `_aggregate` kept as a thin wrapper.
- `tests/test_searches.py`: 10 new tests (20 total) — listing scoping/counts/paging/`status` filter/empty
  dataset/unknown dataset/membership, and idempotency replay, distinct keys, payload conflict, >100-char key
  (`422`), replay-after-worker-run, and replay when `video_ids` was originally omitted.

**Verification:** implementation only in this session — `alembic upgrade head`, `pytest` and `ruff` were not
runnable here (the shell executor is a no-op in this environment). The suite was later confirmed green on
Windows at **121 passed** once the 2026-11-25 lifecycle tests were added; this increment accounted for 114.
Run from `backend/`: `..\.venv\Scripts\python.exe -m alembic upgrade head`, then
`..\.venv\Scripts\python.exe -m pytest -q`, then `..\.venv\Scripts\python.exe -m ruff check app tests`.

## 2026-11-20/21 — Search & SearchVideo: models, migration, fan-out, worker sync, dataset videos, tests

**Goal:** implement the Sprint 3 Search layer (S3-06): one free-text prompt over all ready videos of a dataset,
fan-out to per-video jobs, worker status synchronisation, aggregate search status, and dataset-scoped video
upload/listing — without breaking the legacy project/action/job path.

**Code**

- `app/models.py`: `Search` + `SearchVideo` tables; `SearchStatus` (`queued|running|done|partial|failed`) and
  `SearchVideoStatus` (`queued|running|done|failed`) enums; `Video.dataset_id` and `Candidate.search_id` (nullable
  FK) added; `Video.project_id` and `ProcessingJob.project_id` relaxed to nullable for dataset-only searches.
- `app/schemas.py`: `SearchCreate`, `SearchOut`, `SearchDetailOut`, `SearchVideoOut`; `VideoOut.project_id` and
  `JobOut.project_id` made optional; `CandidateOut.search_id` added.
- `app/api/searches.py` (new): `POST /datasets/{id}/searches` (fan-out, 202), `GET /searches/{id}` (aggregated
  status + counts + per-video list), `GET /searches/{id}/candidates` (review-state/verdict filters).
- `app/api/datasets.py`: `POST/GET /datasets/{id}/videos` (upload via the shared `ingest_video` helper, list).
- `app/api/videos.py`: upload logic extracted into `ingest_video(file, *, subdir, project_id, dataset_id, ...)`;
  `upload_video` is now a thin project wrapper.
- `app/services/pipeline.py`: `enqueue_candidate_job` accepts `action=None`; `_run_candidate_job` sources the
  prompt from `Search` via `SearchVideo` when there is no action and stamps `Candidate.search_id`; worker syncs
  `SearchVideo` status and recomputes parent `Search.status`/`finished_at` on start/success/failure.
- Migrations: `e5b9c3d7a2f1_search_and_search_video.py` (searches + search_videos + video/candidate nullable FK
  columns) and `c9f0d3a1b2e4_nullable_processing_job_project.py` (processing_jobs.project_id nullable).
- `tests/test_searches.py` (new, 9 tests): fan-out skips non-ready videos and stamps `search_id`; requested-video
  filtering + auto title; out-of-dataset video rejection; zero-ready-videos → `done`; status aggregation
  transitions; partial (one fails) and failed (all fail) searches; role + dataset scoping.

**Verification (actual):** `pytest -q` → **103 passed** (2026-11-21; 9 new search tests on top of the prior 94).
Run from `backend/`: `..\.venv\Scripts\python.exe -m alembic upgrade head` then
`..\.venv\Scripts\python.exe -m pytest -q`.

**Not done yet:** re-running existing searches on newly added videos (v1.2 SearchVideo behaviour); dataset-scoped
exports; `DELETE /datasets/{id}/members/{user_id}`. (Search `Idempotency-Key` was added later — see the
2026-11-24 entry.)

## 2026-11-19 — Sprint 3: session auth, invitations and datasets

**PR:** #48 (`feat/auth-datasets`) · **Goal:** implement the first Sprint 3 increment (S3-01…S3-05) without
breaking the existing demo.

**Code**

- `app/security.py`: PBKDF2-HMAC-SHA256 password hashing (260k iterations, per-user salt) and hashed session
  tokens; constant-time verification.
- `app/models.py`: `User`, `Invitation`, `UserSession`, `Dataset`, `DatasetMembership`; global `UserRole`.
- `app/api/auth.py`: bootstrap, login, logout, me, single-use invitations, accept-invitation, user list;
  account lockout after failed attempts.
- `app/api/datasets.py`: dataset CRUD, membership listing/assignment, admin vs dataset-admin scoping.
- `app/deps.py`: `Principal`, session validation, `require_roles`; `VLM_AUTH_REQUIRED` opt-in (default `false`).
- Migration `d03f1c4ffd30_auth_and_datasets.py`; verified with `alembic upgrade head` and `alembic check` on a
  fresh SQLite file, then exercised the API with `create_all` disabled.

**Verification (actual)**

```text
pytest -q                     90 passed (10 new auth/dataset tests)
ruff check app tests          clean
alembic check                 no new upgrade operations
migrated-schema API check     bootstrap 201, login 200, me 200, dataset 201, list 200
```

**Not done yet:** login/invitation UI; refresh tokens and password reset; moving project/video/job routes to
session auth and signed media URLs (R-18); video-to-dataset migration; email transport for invitations.

## 2026-11-15 — Sprint 2 closeout

**Goal:** close Sprint 2 with verified evidence, review/retrospective slides and the Status deck due 16 Nov.

**Verification run (actual)**

```text
pytest -q                     56 passed
ruff check app tests          All checks passed
scripts/smoke_e2e.py          26/26 checks -> docs/evidence/smoke-e2e-20261115-180704.json
npm run build                 PASS (285.93 kB JS / 18.34 kB CSS)
npm test                      21 passed
```

**Artifacts produced**

- `presentations/sprint-02-review.pptx` (11 slides) + Markdown source
- `presentations/sprint-02-retrospective.pptx` (8 slides) + Markdown source
- `presentations/03-status.pptx` (12 slides) + Markdown source
- `docs/sprint-reviews/sprint-02.md`, `docs/retrospectives/sprint-02.md`
- `docs/weekly-reports/week-03.md` (final)
- Sprint backlog closed (77/82 done, 2 blocked, 3 carried over); burndown finalised at 5 SP remaining
- Deliverables register, presentations README and test plan updated

**Not done / unverified**

- No evidence recorded for the 10 Nov presentation or the 13 Nov document submission (team must confirm).
- No client answers from the 13 Nov meeting exist in the repository.
- Real 10–30 min video validation carried to Sprint 3.
- No application code changed in this session.

## 2026-11-12 — Requirements/design alignment with customer answers (documentation only)

**Inputs:** Requirements Definition v1.1, Design Description v1.1 and the Datasets memo (archived in
`docs/inputs/2026-11-12/`), plus the customer emails (CE-1, CE-2) and supervisor emails.
**No application code was changed in this session.**

**Key changes absorbed**

- Dataset Administrators may **invite users**; roles are **global**; accounts are **email-only** (CE-2).
- The MVP loop is `sign-in → dataset → prompt → detection → review → JSON export`; summaries/tags are outside it.
- A **Gemini API key** was supplied (free tier); privacy approval for face-containing videos is the blocker.
- **12 GB VRAM laptops** are offered by the university; 7–8 B bf16 does not fit; API or 4 B quantised is the path.

**Documents updated**

- `docs/REQUIREMENTS.md` → v1.2: 27 FR (DS/PR/DET/REV/EXP/SRCH/USR), 14 NFR, ENG-1…13, KPIs, implementation
  status per requirement, open questions trimmed to the unresolved ones.
- `docs/DESIGN_DESCRIPTION.md` → v1.2: target architecture, data model, auth/roles, search flow, detection
  engine, OpenLABEL JSON proposal, honest implementation status.
- `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/DATABASE_SCHEMA.md`: target v1.2 + current slice.
- `docs/MODEL_EVALUATION.md`: Gemini, VideoJev-4B, test datasets and licences.
- `docs/RISK_REGISTER.md`: R-19…R-26 (scope pivot, privacy approval, key/quota, timeline, VRAM, licences,
  schema, quality).
- `docs/PRODUCT_BACKLOG.md`: epics E10–E13 and PB-43…PB-69.
- `docs/customer/CUSTOMER_DECISIONS.md`: transcription of the emails (no secrets).
- `docs/CLIENT_MEETING_BRIEF_2026-11-13.md` + generated DOCX/PDF for the client meeting.
- `docs/course/DSD_DELIVERABLES_REGISTER.md`, `docs/weekly-reports/week-03.md`, `docs/SPRINT_BACKLOG.md`.

**Verification**

- Markdown link check: 0 missing links across the docs tree.
- DOCX reopened and PDF exported (LibreOffice Kit); 6 pages rendered and visually checked.
- No tests were re-run because no code changed; the last green state remains 56 backend + 21 UI tests.

**Open at the end of the session**

- Requirements/Design v1 submission due **2026-11-13 23:59**; the team's PDFs must be regenerated/reconciled.
- Gemini key redemption status unknown; the one-time link may have expired.
- The customer's OpenLABEL example is still missing from the repository.

## 2026-11-05 — Bootstrap and Sprint 2 vertical slice

**Starting state:** the working directory contained only the prompt pack and a 45-line calendar/register
Markdown file. **No Git repository, no application code, no docs tree.** Week 1 deliverables (Project Plan v1
deck, due 2026-11-02) did not exist. This is recorded as a missed deadline, not backdated.

### Environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Python | 3.14.4 (`.venv` at repo root) |
| Node / npm | 24.22.1 / bundled |
| GPU | RTX 4060 Laptop, 8 GB (no model weights installed) |
| ffmpeg | bundled by `imageio-ffmpeg==0.8.1` |

### Work performed

1. `git init -b main`; `.gitignore` for Python, Node, `data/`, `.env`.
2. Created `backend/` package: config, DB session, SQLAlchemy model (7 tables), Pydantic schemas, validation,
   error envelope, storage, media (ffmpeg probe/clip), adapters (mock + Qwen stub + registry), pipeline
   (enqueue/claim/execute/retry/export), worker CLI, API routers, app factory.
3. Alembic initialised; `0001_initial_schema.py` autogenerated, corrected (custom `UTCDateTime` → `sa.DateTime`
   for DDL), applied to a fresh SQLite database; table set compared with `Base.metadata` → **match**.
4. Wrote 56 pytest tests across validation, storage, projects, videos, flow, worker, security.
5. Wrote `scripts/smoke_e2e.py` (real ffmpeg, real HTTP client, real worker) and generated
   `docs/evidence/smoke-e2e-20261105-170733.json`.
6. Wrote the course artifact set and the design/requirements documentation (see file list in the weekly
   report).
7. Built presentation source and PPTX decks (Project Plan v1, Sprint 1 review, Sprint 1 retrospective,
   Requirements & Design v1) from one content model (`presentations/deckbuild.py`), rendered and visually
   inspected the Requirements & Design cover and table slides with LibreOffice.
8. Built the React UI in `frontend/` (separate workstream) and verified it independently:
   `npm run build` → 41 modules, 285.93 kB JS / 18.34 kB CSS (gzip 86.49 / 4.44), 0 TypeScript errors, and
   `npm test` → 21 tests passing. The UI workstream also ran a **headless Chrome end-to-end pass** against
   the real API/worker (upload, mock job, review, clip playback, export, 375 px layout); its screenshots were
   not retained, so that result is reported rather than independently reproducible (PB-42).
   `GET /` served by FastAPI returns the SPA (200, `text/html`).
9. Started the real server (`uvicorn` on :8010) and probed it with HTTP: `/api/v1/health` → `ok`,
   `/` → 200 HTML, `/api/v1/projects` → `[]`, `/api/docs` → 200.
10. Recorded a limitation found by the UI workstream: `<video src>` cannot send a bearer header, so a
   token-protected deployment breaks playback (R-18, PB-41). Documented in API contracts, install and user
   manuals; token stays off for demos.

### Defects found and fixed during the session (kept for honesty)

| Symptom | Root cause | Fix |
|---|---|---|
| Bearer token not enforced (`/projects` returned 200 without a token) | FastAPI 0.162 / Starlette 1.10 lazy `_IncludedRouter` inclusion dropped the parent router's `dependencies` | Replaced router-level guard with HTTP middleware (secure-by-default) + kept the dependency |
| 500 `TypeError: Object of type ValueError is not JSON serializable` on a blank project name | Pydantic v2 validation `ctx.error` contains an exception object | Error handler now sanitises `ctx` values to primitives |
| Job never retried after a generic adapter failure | Base `AdapterError.retryable = False` by default | Base class now retryable; `AdapterUnavailable` overrides to non-retryable |
| Migration failed with `NameError: app` | Autogenerate emitted `app.models.UTCDateTime` without an import | Migration uses `sa.DateTime(timezone=True)` (DDL-equivalent) |
| `StorageError` module written to `services/__init__.py` by mistake | Mis-targeted write | Moved to `services/storage.py`, package init restored |
| Ruff: 85 findings (B008, StrEnum, imports, etc.) | First-pass code | `ruff --fix`, enums → `StrEnum`, B008 ignored for FastAPI idiom, 3 manual fixes |

### Commands and results

```text
.\.venv\Scripts\python.exe -m pytest -q
56 passed, 1 warning in 5.12s

.\.venv\Scripts\python.exe -m ruff check app tests
All checks passed!

alembic upgrade head (fresh SQLite)  → 7 tables, MATCH with metadata

.\.venv\Scripts\python.exe scripts\smoke_e2e.py
checks: 26/26 passed

cd frontend; npm run build
tsc --noEmit + vite build OK (41 modules, 285.93 kB JS / 18.34 kB CSS)

cd frontend; npm test
2 files, 21 tests passed

uvicorn app.main:app --port 8010  (live)
health ok · / 200 text/html · /api/v1/projects 200 [] · /api/docs 200
```

### Notes / open items

- **No commit was created.** Repository initialised only; committing is left to the team's policy
  (`docs/TEAM_WORKING_AGREEMENTS.md`). `git status` therefore shows every file as new.
- **No upload to the course page** was performed or is claimed.
- `data/` is empty after the session except the ignored default database created by the app factory.
- The frontend workstream was stopped after its build and tests were verified; it did not return a written
  report, so the UI numbers above are the harness's own measured output, not a self-report.
- Deck PPTX files were re-opened with python-pptx (slide counts 16 / 20 / 9 / 8) and spot-rendered; tables
  were tightened after the first render showed an over-tall header row.

## 2026-11-16 — VideoJev-4B engine integrated as the `videojev` adapter

**Goal:** replace the mock-only detector path with the self-hosted zero-shot grounding engine.

**Changed:** `video_grounding/` (library + debug/eval CLI, no HTTP server), `backend/app/adapters/videojev.py`,
`backend/app/services/pipeline.py` (exhaustive adapters), `backend/app/worker.py` (heartbeat lease, cancel),
batch endpoint `POST /projects/{id}/actions/{action_id}/jobs`, `scripts/smoke_videojev.py`;
`fusion.min_event_score` default lowered from 0.9 to 0.5; docs brought in line with this state.

**Results (actual):** Charades-STA, 300 videos / 822 queries, RTX 3070 Laptop 8 GB, `min_event_score` 0.9, before
verify: recall 0.690, precision 0.768, R1@0.5 0.460, mIoU 0.437. Rerun at the new default 0.5: recall 0.771,
precision 0.737, R1@0.5 0.507, mIoU 0.486, queries with no event 12.3% → 1.1%, scan + refine 0.66× the video
duration. All three SPEC targets missed (`video_grounding/docs/EVALUATION.md`).
*Note 2026-11-16 (later): Charades-STA is in-domain for VideoJev, so these numbers are reference only and
`min_event_score` 0.5 is provisional. Main accuracy benchmarks are now the held-out composites
(`video_grounding/scripts/composite_bench.py`), running, results pending.*

**Decisions:** [ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md) (VideoJev-4B is the first
real detector; supersedes the ADR-0004 Alpha target), ADR-0001 amendment (heartbeat lease). Gemini verify exists in
the engine but is off in the adapter. `mock` stays the default adapter.

**Open items:** real-model smoke (`scripts/smoke_videojev.py`) on the RTX 3070 laptop; product-footage validation
(10-30 min videos); peak VRAM at current sampling not recorded; test counts in docs not re-run at this commit.

## Template for the next entry

```markdown
## YYYY-MM-DD — <theme>

**Goal:**
**Changed:** (files/areas)
**Commands run:**
**Results:** (actual output, pass/fail counts)
**Tests added:**
**Decisions:** (ADR links)
**Open items / blockers:**
```
