# Test Plan and Evidence

**Version:** 1.0 · **Date:** 2026-11-05 · **Owner:** QA (role placeholder)
**Related:** [REQUIREMENTS.md](REQUIREMENTS.md) · [API_CONTRACTS.md](API_CONTRACTS.md) · evidence files in
[`docs/evidence/`](evidence/)

## 1. Strategy

| Level | Scope | Tool | Runs where |
|---|---|---|---|
| Unit | Timestamp math, storage safety, mock adapter determinism, retry semantics | pytest | No GPU, no network, <10 s |
| API integration | Every endpoint incl. validation failures, auth, range requests | pytest + FastAPI `TestClient` | In-process, temp SQLite + temp storage |
| End-to-end slice | Upload → job → worker → clips → review → export → unzip | `scripts/smoke_e2e.py` with **real ffmpeg** | Local Windows, ~10 s for a 2-min video |
| Build checks | TypeScript compile + Vite production build, ESLint-level checks | `npm run build` | Node 24 |
| Manual/exploratory | Responsive review UX, keyboard flow, job polling, error display | Browser | Before each demo |
| Acceptance | Course acceptance test cases | see Acceptance Test Plan (Dec) | Sprint 6 |

**Out of scope for this plan:** load/performance testing, penetration testing, multi-browser matrix,
real-model accuracy (handled by the model evaluation protocol), accessibility certification.

## 2. How to run

```powershell
# from the repository root
.\.venv\Scripts\python.exe -m pytest backend -q                 # 56 tests
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
.\.venv\Scripts\python.exe scripts\smoke_e2e.py                 # real ffmpeg, writes evidence JSON
cd frontend; npm ci; npm run build; npm test
```

## 3. Test inventory

| Suite | File | Covers | Count |
|---|---|---|---|
| Timestamp contract | `backend/tests/test_validation.py` | FR-14, FR-16, NFR-03 | 12 |
| Storage safety | `backend/tests/test_storage.py` | FR-03/05, NFR-04/05 | 12 (parametrised) |
| Projects/actions API | `backend/tests/test_api_projects.py` | FR-01, FR-02, NFR-13 | 7 |
| Video API | `backend/tests/test_api_videos.py` | FR-03…FR-07, NFR-02 | 6 |
| End-to-end flow | `backend/tests/test_flow.py` | FR-08, FR-14…FR-26 | 6 |
| Worker/retry | `backend/tests/test_worker.py` | FR-09…FR-13 | 9 |
| Security/adapters | `backend/tests/test_security.py` | FR-28, FR-21, adapter gating | 4 |
| Frontend unit | `frontend/src/lib/format.test.ts` | timestamp formatting | see frontend report |

## 4. Coverage of the riskiest behaviours

| Behaviour | Why it matters | Test |
|---|---|---|
| Unreviewed ≠ negative | Dataset contamination | `test_review_labels_and_unreviewed_export_guard`, `test_include_unreviewed_export_is_explicit` |
| Proposal/preview/correction separation | Auditability and model evaluation | `test_preview_window_keeps_original_boundaries_untouched`, export manifest assertions |
| Interval bounds | Crashes/wrong clips | `test_validate_interval_*`, clamped candidates assertion |
| Atomic job claim | Duplicate processing | `test_claiming_an_empty_queue_returns_false` + conditional UPDATE review |
| Retry idempotency | Duplicate candidates | `test_retryable_adapter_failure_requeues_then_fails`, unique `(job_id, rank)` |
| Path traversal | Arbitrary file read | `test_path_for_rejects_traversal` (6 cases) |
| Range requests | Video seeking | `test_range_request_returns_partial_content` |
| Export correctness | Deliverable quality | `test_export_zip_contains_verified_labels_and_clips`, smoke script archive checks |
| Auth | Footage exposure | `test_bearer_token_is_enforced_when_configured` |

## 5. Actual results (2026-11-05, Windows 11, Python 3.14.4)

| Check | Command | Result |
|---|---|---|
| Backend tests | `.\.venv\Scripts\python.exe -m pytest backend -q` | **PASS — 56 passed, 1 warning** (Starlette deprecation about `httpx` in TestClient) |
| Lint | `.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests` | **PASS — all checks passed** |
| Formatting | `.\.venv\Scripts\python.exe -m ruff format --check backend\app backend\tests` | **PASS after formatting** |
| Migration apply | `alembic upgrade head` on a fresh SQLite file | **PASS — 7 tables match `Base.metadata`** |
| Real ffmpeg E2E | `.\.venv\Scripts\python.exe scripts\smoke_e2e.py` | **PASS — 26/26 checks**, evidence `docs/evidence/smoke-e2e-20261105-170733.json` |
| Frontend build | `npm run build` in `frontend/` | **PASS — 0 TS errors**, 285.93 kB JS / 18.34 kB CSS (gzip 86.49 / 4.44) |
| Frontend unit tests | `npm test` | **PASS — 21 tests** (formatting, hash routing) |
| Browser end-to-end | headless Chrome against the built app + real API/worker | **PASS (reported by the UI workstream; screenshots not retained)** — upload, job polling, 4 candidates, TP save, auto-advance, correction validation, note, reset, clip playback, filters, arrows, project create/delete, export ready, 375 px layout without page overflow |
| Live server probe | `uvicorn` on :8010 | **PASS** — `/health` ok, `/` 200 HTML, `/api/v1/projects` 200, `/api/docs` 200 |
| **Re-verification at Sprint 2 close (2026-11-15)** | pytest, `npm test`, smoke | **PASS** — 56 backend, 21 UI, 26/26 smoke; evidence `docs/evidence/smoke-e2e-20261115-180704.json` |

> Warnings are reported, not hidden: `StarletteDeprecationWarning: Using httpx with starlette.testclient is
> deprecated` comes from FastAPI 0.162 / Starlette 1.10 and does not affect application behaviour.

## 5b. Not exercised

Retry and cancel buttons, `NO_REVIEWED_CANDIDATES`, clicking the ZIP download, UI project PATCH, and a
token-protected deployment were **not** exercised in a browser. Token mode is also functionally blocked for
video playback (`<video>` cannot send the bearer header — R-18).

## 6. Gaps and planned work

| Gap | Impact | Plan |
|---|---|---|
| No real 10–30 min video processed | NFR-02 claims unproven | S2-17 by 2026-11-13 |
| Browser E2E is not committed as a repeatable test | Regressions can slip | Add Playwright in Sprint 4 (PB-42) |
| Retry/cancel/zip-download not browser-tested | Lower confidence in edge paths | Manual pass before 2026-11-15 gate |
| Real VLM inference untested | Core value unproven | Sprint 3 Alpha gate, measured evidence |
| No load/concurrency test | Single-worker assumption undocumented | Documented; revisit with Postgres |
| Postgres untested | Portability claim | Add CI job when deployment needs it |
| Token mode breaks media playback (R-18) | Cannot deploy protected | Signed media URLs (PB-41) before any protected deployment |

## 7. Entry/exit criteria

**Entry:** dependencies installed from the lockfile; database migrated; `data/` writable; ffmpeg resolvable.
**Exit (Sprint 2 gate):** all automated suites green; smoke script 26/26; UI flow manually verified on
desktop and 375 px; no open P0 defect; known limitations listed in the review slides.

## 8. Defect policy

- **P0** (data loss, wrong labels, security): stop and fix before any demo.
- **P1** (broken core flow, misleading UI): fix within the sprint.
- **P2** (cosmetic, edge case): backlog with an ID.
Every defect records: steps, expected, actual, browser/OS, evidence path. No defect is closed without a
reproduction or a test.
