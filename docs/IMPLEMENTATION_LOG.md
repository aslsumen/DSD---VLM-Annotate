# Implementation Log

Chronological record of what was actually built, changed and measured. Newest last.

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
`min_event_score` 0.5 is provisional. Main accuracy benchmarks are now held-out sets: first the small
composites (2026-11-17 entry), then the long-video benchmark (`video_grounding/scripts/heldout_bench.py`,
2026-11-22 entry), which is the current KPI source.*

**Decisions:** [ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md) (VideoJev-4B is the first
real detector; supersedes the ADR-0004 Alpha target), ADR-0001 amendment (heartbeat lease). Gemini verify exists in
the engine but is off in the adapter. `mock` stays the default adapter.

**Open items:** real-model smoke (`scripts/smoke_videojev.py`) on the RTX 3070 laptop; product-footage validation
(10-30 min videos); peak VRAM at current sampling not recorded; test counts in docs not re-run at this commit.

## 2026-11-17 — Held-out composite benchmark results (VideoJev-4B)

**Goal:** check the SPEC targets on data VideoJev was not trained on (PB-70, S3-17).

**Commands run:** `video_grounding/scripts/composite_bench.py` on `youcook2_a`, `youcook2_b`, `bddx`; RTX 3070
Laptop 8 GB, `configs/rtx3070.yaml`, current defaults (`min_event_score` 0.5), found = IoU ≥ 0.3.

**Results (actual, before verify, which is what the product runs):**

| Benchmark | GT | Recall | Precision | CCR | Events per prompt |
|---|---|---|---|---|---|
| `bddx` (driving) | 72 | 0.472 | 0.228 | 0.941 | 21.3 |
| `youcook2_a` (cooking) | 12 | 1.000 | 0.048 | 0.833 | 20.8 |
| `youcook2_b` (cooking) | 12 | 0.750 | 0.044 | 0.778 | 17.2 |

Pooled recall 0.573 (55/96); cooking only 0.875 (21/24). Targets (recall ≥ 0.85, CCR ≥ 0.85) are **not met**
overall: recall only on `youcook2_a`, CCR only on `bddx`. Driving is the weak domain (lane change 2/10, stop for
lead vehicle 0/10); cooking finds the steps but floods the reviewer with false candidates. Optional Gemini verify
keeps every true cooking event and cuts events per prompt by about 85% (to about 3), but on driving it loses 9/34
true events, so it stays off in the product. Scan and refinement together took about 6× the video duration for the 18-prompt batch. A parallel experiment
shared the laptop. Details:
`video_grounding/docs/EVALUATION.md`.

**Open items:** driving recall and cooking precision (PB-71); `min_event_score` 0.5 still provisional, not re-tuned
on the composites (PB-72); product-footage validation.
*Note 2026-11-22: superseded by the long-video benchmark below; these composites had 24 and 72 GT events (recall
CI about ±0.13).*

## 2026-11-20 — Sprint 3 Alpha search resilience

**Base** `a1b8279` · Branch `feat/ui-auth` · DET-3, DS-3, PR-1.

- The dataset and search status views schedule a refresh after the preceding load settles. They stop
  on a terminal state or a 401. A 401 in a signed-in session returns the UI to sign-in.
- If a prompt is saved and the batch enqueue result is unknown or unsuccessful, the form keeps the
  saved action and reuses its enqueue key on retry. The saved search is also available by URL.
  Recovery with the original key applies while the form stays open. The current API saves the action
  and enqueues its jobs in separate calls.

| Check | Result |
| --- | --- |
| `cd frontend && npm run build && npm test` | Build passed. 42 tests passed, including 7 new regressions. |
| `./.venv/bin/python -m pytest -p no:cacheprovider backend -q` | 93 passed. One existing macOS failure in `test_path_for_rejects_traversal` for the backslash case, also reported in PR #42. |
| `./.venv/bin/ruff check --no-cache backend/app backend/tests` | Passed. |
| `./.venv/bin/python scripts/smoke_e2e.py` | 26/26 API and worker checks passed with FFmpeg and the mock detector. |
| Chrome 157, headless, API and worker on local SQLite | Alpha flow passed using the production UI build, auth OFF, an empty static token, a generated 720p MP4, and the mock detector. Verified dataset creation, upload, queued search, results, full-video seek and playback, review, navigation and reload. The JSON download included the accepted interval with its corrected timestamp. |

To repeat the browser check, follow [Plan A](DEMO_RUNBOOK.md#2-plan-a--live-path-68-minutes) with a fresh
demo database. Keep the worker stopped until the queued search survives a reload, then start it against
the same database. For the fault checks, intercept only these requests in a local browser test:

1. Forward the initial batch enqueue to FastAPI, confirm the upstream `202`, then drop its response.
   On the original build the next submit sent another create-action request and got `409`. The fixed
   build sends one create-action request in total, reuses the batch URL and `Idempotency-Key` and leaves
   one job for the fixture video. Two form submits in the same tick also leave one saved action.
2. While the search is queued, delay one `GET /api/v1/jobs` refresh for 3.4 seconds. The original build
   started the next refresh before that request finished. The fixed build waits for it to settle.
3. In a separate signed-in browser context on the queued search, return a test-only `401 INVALID_SESSION`
   from the jobs refresh. The original build kept polling. The fixed build returned to sign-in after one
   401 and made no further polls.

These checks used Chrome on macOS and Node 22.23.2. Firefox, Edge and VideoJev inference were outside
this run. Project/job session enforcement, Dataset membership for the workflow and protected playback
remain backend dependencies. The browser 401 was injected because the current jobs route still uses
the legacy static-token guard.

## 2026-11-22 — Held-out long-video benchmark results (VideoJev-4B)

**Goal:** replace the small composites as the KPI source (PB-70). The user judged them too small to be reliable:
24 cooking and 72 driving GT events, recall CIs of about ±0.13. Switched 2026-11-20.

**Commands run:** `video_grounding/scripts/heldout_bench.py` `select`, `prep`, `score`. One scan job per video, no
concatenation. YouCook2 validation split: 33 videos, 3.65 h, 300 steps, 29 recipes; prompts are the video's own steps
plus 3 absent steps from other recipes (12.1 per video). ROAD (ego-action labels at 12 fps): 20 videos, 2.75 h, 238
events; prompts are the six ego actions plus the absent prompt "the ego vehicle collides with another vehicle".
Videos are 5 to 30 min. RTX 3070 Laptop 8 GB with about 3 GB offloaded, `configs/rtx3070.yaml`, Gemini verify off,
engine defaults (coarse 1 fps / 32 frames, refine 2 fps / 64 frames, `min_event_score` 0.5). Run 2026-11-20 10:40 to
2026-11-22 01:31, 0 failed units. Selections: `video_grounding/benchmarks/heldout_youcook2.json`, `heldout_road.json`.

**Results (actual, 95% bootstrap CI over videos):**

| | YouCook2 | ROAD |
|---|---|---|
| Recall | 0.86 [0.81, 0.90] (258/300) | 0.47 [0.39, 0.56] (112/238) |
| CCR | 0.78 [0.70, 0.85] | 0.82 [0.72, 0.91] |
| Mean boundary adjustment | 4.2 s [3.5, 5.0] | 7.9 s [5.6, 11.1] |
| Candidates per present / absent prompt | 5.9 / 3.5 | 9.2 / 8.4 |
| Total time ÷ video length (all prompts in one job) | 5.72 | 4.71 |

ROAD recall by prompt: turn right 42/48, turn left 32/54, stop 35/100, overtake 3/12, move left 0/12, move right
0/12. Targets (recall ≥ 0.85, CCR ≥ 0.85): cooking recall 0.86 meets it as a point estimate but the lower bound is
0.81, so it is not confirmed; cooking CCR 0.78 misses. Driving misses widely: turns are found, lateral moves
(0/24), overtakes and most stops are not, and absent prompts give almost as many candidates as present ones, so the
model barely tells present from absent on driving. On cooking, absent prompts give fewer candidates than present
ones. The composite results (cooking 0.875, driving 0.47) agree in direction and are superseded. These timings measure multi-prompt benchmark jobs. The separate [single-prompt measurements](../video_grounding/docs/EVALUATION.md#speed-kpis)
report the elapsed job time for each video and prompt.

**Open items:** driving recall and absent-prompt false candidates (PB-71); `min_event_score` sweep (PB-72);
product-footage validation.

## 2026-11-25 — Phase 3A: frontend session hardening

**Base** `a3fa00c` (includes PR #52) · Local branch `feat/ui-auth-session` · USR-1, USR-2,
USR-5, NFR-12, NFR-13.

On the baseline, a network error, 403 or 5xx could open Development mode during bootstrap. A
malformed 200 could also mount protected UI. The frontend now grants anonymous access after a
validated HTTP 200 from the real Dataset list. Without credentials, a 401 shows sign-in. A stored
bearer token is verified with `GET /api/v1/auth/me`; a 401 clears it and requires sign-in. Other
failures gate the workspace and let the user retry.

One session check at a time runs at 30-second intervals after completion. On a failed check, the
workspace closes until the server confirms the retained token. A successful check refreshes the
role. Storage changes from other tabs invalidate earlier work, and cancelled or superseded responses
cannot reopen the workspace. A closed workspace cancels its fetches, uploads and scheduled
refreshes. Logout attempts server revocation with the previous bearer token and reports if that
could not be confirmed. Sign-in resumes protected hash routes and unsaved review times and notes
are restored in memory for the same user after reauthentication.

| Check | Baseline | Phase 3A |
| --- | --- | --- |
| Frontend Vitest | 42 passed | 80 passed |
| TypeScript and Vite production build | Passed | Passed |
| Backend pytest (macOS) | 98 passed, one failed | 98 passed, same failure ([#55](https://github.com/aslsumen/DSD---VLM-Annotate/issues/55)) |
| Focused auth and Dataset API pytest | 10 passed | 10 passed |
| Ruff lint / format check | Lint passed, 10 files flagged by format check | Same |
| Fresh SQLite Alembic upgrade/current/check | `d03f1c4ffd30` head, no pending operations | Same |
| FFmpeg + mock smoke | 26/26 | 26/26 |

The Chrome evidence and Playwright reproductions for the local review are stored outside the Git
diff. The browser checks use isolated SQLite databases, synthetic accounts and generated video.
Auth ON covers fail-closed bootstrap, route guards, late responses, revocation and review recovery.
Auth OFF exercises the Alpha flow including the lost enqueue response and serialized polling from
PR #52, full-video playback, a corrected annotation and JSON download.

**Backend dependencies:** Legacy Project, Action, Job, media and annotation endpoints still require
their own authorization and Dataset membership enforcement. The implemented session has server-side
absolute expiry, while the v1.2 inactivity policy remains pending. Browser cancellation cannot undo
already committed writes. The tests use Chromium on macOS, SQLite and the mock detector. Phase 3B
is the independent review gate.

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
