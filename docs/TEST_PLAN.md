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
real-model accuracy (handled by the model evaluation protocol and `video_grounding/docs/EVALUATION.md`), accessibility certification.

## 2. How to run

```powershell
# from the repository root
.\.venv\Scripts\python.exe -m pytest backend -q                 # 162 tests
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
| VideoJev adapter | `backend/tests/test_videojev.py` (fake engine, no torch) | exhaustive pipeline, batch endpoint, resume, cancel | added 2026-11-16 |
| Heartbeat lease | `backend/tests/test_lease.py` | PB-28 / R-07 | added 2026-11-16 |
| Searches | `backend/tests/test_searches.py` | search fan-out, status aggregation, role + dataset scoping, dataset search listing (`GET /datasets/{id}/searches`, paging + `status` filter), `Idempotency-Key` replay/conflict, job-lifecycle sync (cancel / reaper requeue+exhausted / retry / video delete), concurrent completion, job/SearchVideo/Search consistency (fenced start, single-transaction mirror, `reconcile_search_state` sweep), video deletion atomicity and the job cascade, idempotency request scope (stored snapshot, must-match fields, legacy fallback), search-level cancel / restart | added 2026-11-21 (S3-06/S3-16), extended 2026-11-24 (20 tests), extended 2026-11-25 (35 tests), extended 2026-11-26 (51 tests) |
| Review filters | `backend/tests/test_review_filters.py` | `review_state` and `verdict` combined on both candidate listings; verdict alone; `unreviewed + verdict` stays empty | added 2026-11-25 (3 tests) |
| Dataset authorization | `backend/tests/test_dataset_authz.py` | 401/404/403 matrix on the shared legacy routes (`/videos/{id}`, `/jobs/*`, `/candidates/*`) for administrator, `dataset_admin` member, annotator member, non-member and anonymous; refused mutations leave row, file and status untouched; project-owned rows keep their unauthenticated behaviour | added 2026-11-25 (9 tests) |
| Frontend unit | `frontend/src/lib/format.test.ts` | timestamp formatting | see frontend report |

## 4. Coverage of the riskiest behaviours

| Behaviour | Why it matters | Test |
|---|---|---|
| Unreviewed ≠ negative | Dataset contamination | `test_review_labels_and_unreviewed_export_guard`, `test_include_unreviewed_export_is_explicit` |
| Proposal/preview/correction separation | Auditability and model evaluation | `test_preview_window_keeps_original_boundaries_untouched`, export manifest assertions |
| Interval bounds | Crashes/wrong clips | `test_validate_interval_*`, clamped candidates assertion |
| Atomic job claim | Duplicate processing | `test_claiming_an_empty_queue_returns_false` + conditional UPDATE review |
| Concurrent search completion | Search stuck `running` for ever | `test_concurrent_completion_settles_the_search` |
| Cancel reap race with job start | Canceled video resurrected to `running`, search stranded | `test_execute_job_does_not_resurrect_a_canceled_video` |
| Drift repair | Job and `SearchVideo` disagree after a crash; search never settles | `test_reconcile_repairs_a_video_left_running_by_a_crashed_job`, `test_reconcile_repairs_a_requeued_job_and_settles_an_idle_search` |
| Stale aggregate after a kill | Child rows committed, aggregate never derived; reaper cannot see it (no stale job) | `test_reconcile_settles_a_search_whose_videos_all_finished` |
| Video deletion atomicity | Crash mid-delete leaves the video alive but its search `done` with zero videos | `test_video_delete_rolls_back_with_its_search_settle` |
| Deletion under a running job | Job stranded `running` with no video, then `PendingRollbackError` | `test_deleting_a_video_mid_run_does_not_strand_the_job`, `test_deleting_a_video_cascades_its_jobs_and_candidates` |
| Idempotent replay after a delete | Identical request starts returning 409 because its video is gone | `test_idempotent_replay_survives_deleting_the_selected_video`, `test_legacy_search_without_a_stored_scope_still_replays` |
| Idempotency request identity | Same key with changed params/scope silently reusing the old search | `test_idempotency_key_reuse_with_different_params_conflicts`, `test_idempotency_key_reuse_switching_from_subset_to_all_conflicts`, `test_idempotency_key_reuse_with_different_adapter_conflicts`, `test_idempotency_key_conflict_lists_every_mismatched_field` |
| Search cancel / restart | Frontend cannot stop a run or restart only the failures | `test_search_cancel_cancels_every_video_and_settles_the_search`, `test_search_retry_requeues_only_the_failed_videos`, `test_search_retry_without_failures_is_refused`, `test_search_cancel_and_retry_respect_the_dataset_boundary` |
| Concurrent cancellation | Worker resumes a job whose search was canceled mid-claim and un-settles it | `test_search_cancel_wins_against_a_worker_that_already_claimed` |
| Review filter combination | `review_state` + `verdict` → 500 | `test_project_candidates_filter_by_review_state_and_verdict`, `test_search_candidates_filter_by_review_state_and_verdict` |
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
| **Re-verification (2026-11-26)** | `python -m pytest backend -q` and `python -m ruff check backend/app backend/tests` (`python` = `.venv/Scripts/python.exe`) | **PASS — 162 passed, 0 failed** and ruff clean, run by the team on Windows after the idempotency request-scope work |

> Results above are the Sprint 2 baseline (2026-11-05/15). Since then the backend suite grew to 80 tests (`test_videojev.py`, `test_lease.py`; 2026-11-16, not re-run for this document), then to 90 tests with the auth/dataset PR #48 (2026-11-19), to **103 tests** with `test_searches.py` (9 tests, 2026-11-21 — all green), to **114 tests** with the dataset-search listing + `Idempotency-Key` work (10 more tests in `test_searches.py`, 2026-11-24), and to **121 tests** with the job-lifecycle regression tests (7 more, 2026-11-25 — all green), and to **125 tests**
with the review-filter and concurrent-completion tests (4 more, 2026-11-25 — all green), to **134 tests** with the dataset-authorization matrix on the shared legacy routes (9 more in `test_dataset_authz.py`, 2026-11-25), to **137 tests** with the job/SearchVideo/Search consistency tests (section 7 of `test_searches.py`, 2026-11-25), to **146 tests** with the video-deletion tests (section 8, 2026-11-25), and to the current suite: **154 test functions**, which pytest reports as **162 collected** because `test_storage.py::test_path_for_rejects_traversal` expands to 6 cases and `test_worker.py::test_only_failed_jobs_are_retryable` to 4 (the idempotency request-scope and search cancel/restart tests added 15 in section 9 of `test_searches.py`, plus a concurrent-cancellation case, 2026-11-26). Where the counts above say "103/114/121/125/134/137/146" they were function counts carried forward by arithmetic; use the number pytest prints when quoting the suite. The engine has its own suite (`video_grounding/tests`, 44 tests on macOS at the last count in `EVALUATION.md`).

> Warnings are reported, not hidden: `StarletteDeprecationWarning: Using httpx with starlette.testclient is
> deprecated` comes from FastAPI 0.162 / Starlette 1.10 and does not affect application behaviour.

## 5b. Not exercised

Retry and cancel buttons, `NO_REVIEWED_CANDIDATES`, clicking the ZIP download, UI project PATCH, and a
token-protected deployment were **not** exercised in a browser. Token mode is also functionally blocked for
video playback (`<video>` cannot send the bearer header — R-18).

## 6. Gaps and planned work

| Gap | Impact | Plan |
|---|---|---|
| No 10–30 min customer video run through the web flow | NFR-02 claims unproven | S2-17 by 2026-11-13 |
| Browser E2E is not committed as a repeatable test | Regressions can slip | Add Playwright in Sprint 4 (PB-42) |
| Retry/cancel/zip-download not browser-tested | Lower confidence in edge paths | Manual pass before 2026-11-15 gate |
| Real-model validation on product footage | The 52-second public-clip web smoke passed on the RTX 3070 laptop on 2026-11-23. Held-out long-video recall was 0.86 for cooking and 0.47 for driving, with complete-clip rates of 0.78 and 0.82. See the [release notes](RELEASE_NOTES.md) and [evaluation report](../video_grounding/docs/EVALUATION.md) | Sprint 3 Alpha gate, measured evidence |
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
