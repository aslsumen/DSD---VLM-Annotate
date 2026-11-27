# Sprint Backlog — Sprint 3 (2026-11-16 → 2026-11-29)

**Type:** living artifact · **Owner:** Scrum Master (role placeholder) · **Created:** 2026-11-15 (draft)
**Sprint goal:** *By 2026-11-29, a user can sign in with a global role, see only assigned datasets, run one
prompt over all videos of a dataset, review candidates across videos, and export OpenLABEL-based JSON — with a
real detector (self-hosted VideoJev-4B; Gemini as an optional verify stage) measured on a public test set.*

**Capacity:** still **UNKNOWN** (no declared availability). Estimates are provisional story points, not hours.
Target 80–85 % of declared capacity once the table is filled.

> **Status note 2026-11-16 (detector work):** the plan above is unchanged. The real detector is VideoJev-4B
> through the `videojev` adapter ([ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md)), not
> Gemini; Gemini exists only as an optional engine verify stage, off in the adapter. S3-11 is superseded,
> S3-12 is done (Charades-STA only), S3-13 is partly done (engine `eval` CLI). Charades-STA is reference only (VideoJev
> was trained on it); the SPEC target check moved to the held-out long-video benchmark (S3-17, done 2026-11-22: recall 0.86 cooking /
> 0.47 driving vs 0.85, targets not met or not confirmed; `video_grounding/docs/EVALUATION.md`). A 52-second public clip passed the real VideoJev web smoke on the RTX 3070 laptop on 2026-11-23.

## 1. Committed scope (Must)

| ID | Task | Refs | Est. | Owner (role) | Notes |
|---|---|---|---|---|---|
| S3-01 | Auth data model + migration: users, invitations, sessions, dataset memberships (planned as `dataset_assignments`; implemented as `dataset_memberships`) | USR-1…5, NFR-11 | 8 | Backend | **PR #48** — migration verified |
| S3-02 | Auth API: login/logout/refresh, password hashing, session revocation, lockout | NFR-12…14 | 8 | Backend | **In review** — login/logout/session/lockout; refresh pending |
| S3-03 | Invitation flow + email abstraction (SMTP/provider) | USR-5 | 5 | Backend | **In review** — token returned once; no SMTP transport yet |
| S3-04 | RBAC middleware + dataset scoping on every route | USR-2/3/4 | 5 | Backend | **Done (API) 2026-11-25** — roles enforced on the auth/dataset/search routes by `require_roles`/`_require_access`, and on the shared legacy video/job/candidate routes by `backend/app/access.py` (anonymous → 401, non-member → 404 hiding existence, wrong role → 403), covered by `backend/tests/test_dataset_authz.py` (9 tests). Frontend route guards still missing |
| S3-05 | Dataset entity + API + assignments (migrate Project) | DS-1/2/3 | 8 | Backend | **Done (API) 2026-11-19/20** — `datasets` + `dataset_memberships` (the plan said `dataset_assignments`; the implemented table has a surrogate `id` and a unique `(dataset_id, user_id)`, with no `assigned_by`/`assigned_at`), `POST/GET /datasets/{id}/videos`, `videos.dataset_id`. `projects` remains untouched for the legacy slice; membership revocation, the data migration and the frontend cutover are still open |
| S3-06 | Search entity: one prompt over all videos, fan-out jobs, status aggregation | PR-1, DET-3 | 8 | Backend | **Implemented 2026-11-20** — models + migration (`e5b9c3d7a2f1`, `c9f0d3a1b2e4`), `POST /datasets/{id}/searches` fan-out, worker sync, aggregated status, read endpoints; tests added 2026-11-21. **Extended 2026-11-24** — `GET /datasets/{id}/searches` (list + `status`/`limit`/`offset`) and `Idempotency-Key` on search creation (migration `f1a4b8c2d6e9`) |
| S3-07 | UI: login, invitation acceptance, user management | USR-1…7 | 5 | Frontend | Route guards |
| S3-08 | UI: datasets list/detail, upload, search launch, search history | DS-1…3, PR-1 | 8 | Frontend | Reuse upload component |
| S3-09 | Cross-video review list, accepted/rejected vocabulary, review flags | REV-1…4 | 5 | Frontend | Pagination |
| S3-10 | OpenLABEL-based JSON export (multi-interval) + async job | EXP-1 | 8 | Backend | Schema confirmed with customer |
| S3-11 | Gemini adapter: `GroundingBackend`, quota guard, retry, JSON validation | DET-1, NFR-6 | 8 | ML | **Superseded 2026-11-16** by the `videojev` adapter (ADR-0007). Gemini is only the engine's optional verify stage (off in the adapter); privacy approval R-20 matters only if verify is on |
| S3-12 | Test-data ingestion (Charades-STA subset) + licence check | NFR-5 | 5 | ML | Done 2026-11-16 (Charades-STA only). Non-commercial caveat |
| S3-13 | KPI harness: recall, R@IoU, complete clip, boundary adjustment | NFR-5 | 5 | ML | First measurements done 2026-11-16 (engine `eval` CLI; Charades-STA reference only, held-out benchmark in S3-17); reviewer boundary-adjustment KPI not built |
| S3-14 | Alpha deck + evidence + upload checklist | D-19 | 5 | Scrum Master | Upload 2026-11-30 |
| S3-15 | Carry-over: validate a real 10–30 min video | NFR-4 | 3 | QA | From Sprint 2 |
| S3-16 | Integration tests: auth, permissions, dataset scoping | NFR-11…14 | 5 | QA | Security-critical. **Done 2026-11-21** — `backend/tests/test_searches.py` (9 tests) covers search fan-out, status aggregation, role + dataset scoping; full suite 103 passed. **Extended 2026-11-24** — 10 more tests for dataset search listing and `Idempotency-Key` (20 in the file, 114 total). **Extended 2026-11-25** — 7 lifecycle regression tests for cancel / reaper / retry / video delete (27 in the file, 121 total). **Extended again 2026-11-25** — `test_review_filters.py` (3) + concurrent-completion test (28 in `test_searches.py`), 125 total. **Extended once more 2026-11-25** — `test_dataset_authz.py` (9) for the shared-route authorization matrix, 134 total. **And again 2026-11-25** — 3 consistency tests in section 7 of `test_searches.py` (31 in the file), 137 total. **Plus 2026-11-25** — a fourth (`test_reconcile_settles_a_search_whose_videos_all_finished`, the kill between the child commit and the aggregate) and a `reconcile_search_state` return-value fix (32 in the file), 143 total. **One more 2026-11-25** — 3 video-deletion tests in section 8 (35 in `test_searches.py`) and a rewritten `test_dataset_authz.py::test_job_whose_video_was_deleted_fails_closed`, 146 total. **Latest 2026-11-26** — 15 tests in section 9 for the idempotency request scope and search-level cancel / restart, plus a concurrent-cancellation case (51 in `test_searches.py`), 162 total. **Extended 2026-11-27** — 4 concurrent-restart tests (55 in `test_searches.py`), 166 total. **Latest 2026-11-27** — 3 reconciliation tests (58 in the file), 169 total. **Durable cleanup 2026-11-27** — `test_storage_gc.py` (9 tests) for the deletion queue, the post-commit crash window and the late preview clip, 178 total. **Preflight fix 2026-11-27** — 1 regression test for a canceled job whose adapter lookup then fails (59 in `test_searches.py`), 179 total |
| S3-17 | Run held-out benchmarks (long YouCook2 and ROAD videos), re-check `min_event_score`, report KPIs | NFR-5 | 5 | ML | **Done** 2026-11-22 on the RTX 3070 laptop (PB-70): recall 0.86 cooking (CI 0.81–0.90) / 0.47 driving, CCR 0.78 / 0.82, targets not met or not confirmed; absent prompts give 3.5 / 8.4 candidates; `min_event_score` 0.5 checked, not re-tuned (PB-72). Earlier small composites (2026-11-17) superseded |

**Status 2026-11-19:** S3-01…S3-05 implemented in PR #48 (10 new tests, 90 total); JSON schema is in PR #47
(docs only).

**Status 2026-11-20/21:** S3-06 implemented (Search/SearchVideo models + migrations `e5b9c3d7a2f1` +
`c9f0d3a1b2e4`, search fan-out endpoint, worker status sync + aggregation, dataset video upload/listing, read
endpoints). `backend/tests/test_searches.py` (9 tests) added for S3-16. Re-run-on-new-videos and dataset-scoped
exports remain open.

**Status 2026-11-24:** the frontend needed a search-history endpoint on page reload, so `GET
/datasets/{id}/searches` (paged, `status` filter, per-status counts in one aggregate query) and an
`Idempotency-Key` header on search creation were added — key stored on `searches.idempotency_key` (global
unique, migration `f1a4b8c2d6e9`), replaying returns the existing search, changed payload → `409
IDEMPOTENCY_KEY_REUSED`. `test_searches.py` grew to 20 tests (114 total).

**Status 2026-11-25:** the three lifecycle paths that could strand a search were fixed — `cancel_job` now marks
its `SearchVideo` `failed` with `"Job canceled"`, `reap_stale_jobs` mirrors the requeue/fail decision onto the
video row, `retry_job` reopens it, and `delete_video` drops the `SearchVideo` rows and re-derives the search
(`refresh_searches_for_video`); a search whose last video is deleted settles as `done` instead of hanging. No
migration — canceled jobs map to `SearchVideoStatus.failed` rather than a new enum member. 7 regression tests
added (27 in `test_searches.py`, 121 total, green 2026-11-25).

**Status 2026-11-25 (later):** two defects from PR review fixed. `review_state` + `verdict` on the candidate
listings no longer join `annotations` twice (that combination returned `500`); `annotations` is joined at most
once on both `GET /projects/{id}/candidates` and `GET /searches/{id}/candidates`. Concurrent completion of the
last two videos of a search no longer leaves it `running`: the `SearchVideo` row is committed **before** the
aggregate is derived (`_settle_search_status`, re-derived until stable), so a peer worker always sees it. New
`test_review_filters.py` (3 tests) plus `test_concurrent_completion_settles_the_search` — 125 total, green.
Still open from the same review at the time: the legacy `/videos/{id}` and `/candidates/{id}` routes had no dataset
membership check when `VLM_API_TOKEN` is unset — closed in the entry below.

**Status 2026-11-25 (dataset authorization):** the merge-blocker from the same review is fixed. The shared legacy
routes (`GET/DELETE /videos/{id}`, `GET /videos/{id}/stream`, `GET /jobs`, `GET /jobs/{id}`, retry, cancel,
`GET /jobs/{id}/candidates`, `GET/PUT/DELETE /candidates/{id}*`) now resolve the dataset that owns the row
(`app/access.py`) and apply the same rules as the dataset routes: `401` for an anonymous caller once the row is
dataset-owned, `404` for a signed-in non-member whatever the global role (existence must not leak), `403` for a
member without the write role. `GET /jobs` filters instead of refusing. Rows belonging to no dataset keep their
historical unauthenticated behaviour, which is why the handlers use the new `get_optional_principal` rather than a
required dependency — and annotation writes need membership only, not a write role. New
`backend/tests/test_dataset_authz.py` (9 tests) covers the four-caller matrix and asserts refusals have no side
effects. 134 total. Owner-unattributable rows (a search job whose video was deleted) are administrator-only.

**Status 2026-11-25 (job / SearchVideo / Search consistency):** the third defect in that review — state diverging
across the three levels when a worker is interrupted — is fixed. Every write path (`_finish`, `_record_failure`,
`fail_job_now`, `retry_job`, `reap_stale_jobs`, `cancel_job`) now commits the job row and its `SearchVideo` mirror in
one transaction and only then derives the aggregate; the first child write in `execute_job` is fenced against job
ownership, so a cancel landing between the claim and the start is no longer overwritten. The worker also runs a new
`reconcile_search_state` sweep each tick: it repaints a `SearchVideo` that disagrees with its job (the job is the
source of truth, `canceled` → `failed` / `"Job canceled"`) and re-derives any Search still `queued`/`running`/`partial`
whose videos have all settled. It is idempotent and returns 0 on a consistent database. No migration — pure Python,
and the search enums still match `DESIGN_DESCRIPTION.md:121` (no `canceled` member). Four tests in section 7 of
`backend/tests/test_searches.py` (32 in the file); **143 tests collected** (135 test functions, two of them
parametrised). **Plus 2026-11-25** — 3 video-deletion tests in section 8 (35 in the file), 146 total.

**Status 2026-11-25 (consistency follow-up):** a PR harness reported the exact windows; two needed more work.
`reconcile_search_state` now counts both repairs it can perform, so a sweep that only settles a stale aggregate
reports 1 instead of 0 (it used to read as "consistent"). A fourth test,
`test_reconcile_settles_a_search_whose_videos_all_finished`, pins the child-committed/aggregate-stale window, which
`reap_stale_jobs` cannot see because no job is stale — the per-tick sweep is the only thing that repairs it.

**Status 2026-11-25 (video deletion):** `DELETE /videos/{id}` is now one transaction with its search settle.
`refresh_searches_for_video` and `_settle_search_status` grew a `commit=False` mode, so the endpoint detaches the
video's `SearchVideo` rows, deletes the `Video` row and commits, and only then converges the affected Searches
(afterwards on purpose: the derivation has to see a peer worker's committed row). Storage files are removed only
after that commit. `Video.jobs` declares `passive_deletes=True`, so deleting a video now cascades to its jobs and
candidates instead of nulling `processing_jobs.video_id` and leaving an ownerless `running` job, and `execute_job`
gained an `except SQLAlchemyError` branch that rolls back, re-reads the job and either returns (row gone or taken
over) or fails it cleanly — a failed statement no longer escapes as `PendingRollbackError`. No migration: the DDL
already declared the cascade, this is an ORM relationship option plus Python. Three tests in section 8 of
`backend/tests/test_searches.py` (35 in the file), and `test_dataset_authz.py::test_job_whose_video_was_deleted_fails_closed`
now builds its ownerless job with a raw update; **146 tests collected** (138 test functions, two of them
parametrised).

**Status 2026-11-26 (idempotency request scope and search cancel / restart):** the review's first finding — an
`Idempotency-Key` replay was compared against *live* `search_videos` rows, so deleting a selected video made the
original request stop matching itself (409), and `params` / an omitted `video_ids` were never compared at all — is
closed by persisting the request on the row: migration `b8d2e5a4c9f3` adds `searches.request_scope_json` (NOT NULL
`Text`, `{}` server default for existing rows), holding a canonical JSON snapshot of `dataset_id`, `prompt`,
`params`, the resolved `adapter_name` and the requested `video_ids` (`null` distinct from any subset, order and
duplicates erased). Replay now compares that snapshot and never the live rows; `409 IDEMPOTENCY_KEY_REUSED` carries
`details.mismatched_fields`; `title` is deliberately not part of the identity, and a legacy `{}` row falls back to
the old rule with a warning. The second cutover dependency, cancel/restart, adds
`POST /datasets/{id}/searches/{search_id}/cancel` (200, a no-op once settled) and `.../retry` (202, re-queues only
failed videos, `409 SEARCH_NOT_RETRYABLE` otherwise), both `dataset_admin` and both routed through `cancel_job` /
`enqueue_candidate_job` so there is still one writer per state. No table dropped or renamed. Sixteen tests in
section 9 of `backend/tests/test_searches.py` (51 in the file); **162 tests collected** (154 test functions, two of
them parametrised). **Confirmed green:** `pytest -q` reported **162 passed** and `ruff check` was clean, run by the
team on Windows on 2026-11-26. Migration `b8d2e5a4c9f3` still needs an explicit `alembic upgrade head` — the
fixtures build their schema with `Base.metadata.create_all`, so a green suite does not exercise it.

**Status 2026-11-27 (concurrent search restart and reconciliation):** three more findings from the same review, all
in the recovery paths. Two concurrent `POST .../searches/{id}/retry` requests used to insert a replacement job each
and overwrite each other's link, leaving one queued job attached to no `SearchVideo` — the restart is now a
compare-and-swap on `(row id, old job id, status = failed)`, the loser deletes its own job and answers 202 with the
current state, and `POST /jobs/{id}/retry` on a superseded search job (`candidate_proposal` with `action_id IS NULL`
and no `SearchVideo` pointing at it) answers `409 JOB_SUPERSEDED`. `reconcile_search_state` used to write back a
page it had read earlier, so a video finishing inside that window was dragged from `done` back to `running`; each
repaint is now a conditional update that re-asserts both the observed `SearchVideo` status and the job status, and a
row that moved on is skipped for the next tick. The sweep also settles a *terminal* parent (`done`/`failed`) that
still has a `queued`/`running` video, which is the state `retry_search` leaves if the process dies between its commit
and its aggregate settle. No migration. Seven tests in sections 7 (reconciliation) and 9 (restart) of
`backend/tests/test_searches.py` (58 in the file); **169 tests collected**. The reconciliation tests are written but
not yet run for this document — the restart tests were the ones the last `pytest -q` run exercised.

**Status 2026-11-27 (durable storage cleanup):** the fourth finding of the review: `DELETE` committed its rows and
unlinked the bytes afterwards, so a crash in between stranded the source file, its clips and its `engine/` scratch
directories with no row left to name them (reviewer 3A), and a preview clip extracted for a video that was deleted
while the extractor was paused was never referenced by anything (3B, reproducible on `main` through the legacy
workflow). The delete now writes `pending_deletions` intent rows **in the same transaction** as the row delete — so
"the row is gone" implies "the cleanup is still queued" — and drains them afterwards; the worker drains the queue on
every tick (`purge_storage`, before claiming a job, guarded so a locked file cannot stop processing), and every delete
endpoint (`/videos/{id}`, `/projects/{id}`, `/actions/{id}`, `/exports/{id}`) flushes the keys it just queued. The same
sweep collects the two places a late writer can create an unreferenced key — orphaned preview clips and `engine/`
directories whose job/video is gone — with an ownership check first and a `VLM_STORAGE_GC_GRACE_SECONDS` (default
300 s) age gate, so it never races a live extraction; a feature cache for a video that still exists is kept. The
preview-clip loop now fences *before* writing and re-checks its candidate row afterwards, so 3B no longer produces the
orphan at all. Migration `0007`/`c4f7a1e9b2d5` (`pending_deletions`) is new; `pending_deletions` is the 15th table.
`backend/tests/test_storage_gc.py` adds 9 tests (interrupted delete, dead-process sweep, late clip, grace period,
engine directories kept by ownership, unusable key, rolled-back and failed deletes); **179 tests collected** — the
storage tests are written but not yet run
for this document.

**Status 2026-11-27 (preflight after a cancel):** the worker claims a job and only then resolves the model adapter;
a failure in that lookup called `fail_job_now`, which wrote `failed` without checking ownership, so a cancel that
landed in that window was overwritten and the `SearchVideo` carried the adapter error instead of "Job canceled".
`fail_job_now` now fences on `(id, status='running', attempts)` first, like `execute_job`, and gives up when the job
is no longer its own. One regression test
(`backend/tests/test_searches.py::test_preflight_failure_does_not_resurrect_a_canceled_job`) — **179 tests
collected** with it, not yet run for this document.

**Total committed:** ~99 SP. **This is likely more than the team can absorb in two weeks without capacity
data** (R-22). Triage proposal: S3-01…S3-07 and S3-14 are the minimum; S3-08…S3-13 can slip into Sprint 4 if
the detector or JSON schema is blocked.

## 2. Daily plan (working days only)

| Date | Focus | Gate |
|---|---|---|
| Mon 16 Nov | Upload Status deck (23:59); auth data model; confirm capacity | deck evidence |
| Tue 17 Nov | Status presentation; auth API; JSON schema proposal to customer | feedback recorded |
| Wed 18 Nov | RBAC middleware; dataset entity migration | two roles enforced |
| Thu 19 Nov | Search entity + fan-out; UI login | sign-in works end-to-end |
| Fri 20 Nov | Invitations; dataset UI; real-video validation | invite → sign-in works |
| Mon 23 Nov | JSON export v1; real-model smoke on the 8 GB laptop (replaces the Gemini adapter spike) | first JSON export |
| Tue 24 Nov | Cross-video review; review flags | one list across videos |
| Wed 25 Nov | KPI harness; held-out benchmark results (S3-17); product-footage run | KPI numbers on product footage |
| Thu 26 Nov | Integration tests; fix defects | tests green |
| Fri 27 Nov | Alpha deck draft; limitations documented | deck source ready |
| Sat 28 Nov | **No work assumed** | — |
| Sun 29 Nov | Sprint 3 gate: Alpha prototype testable | PASS/FAIL evidence |

## 3. Exit criteria (Alpha gate, 2026-11-29)

- [ ] Sign-in with global roles; users see only assigned datasets
- [ ] Invitation flow works (single-use, 48 h)
- [ ] Search over all videos of a dataset returns candidates
- [ ] Review across videos with accept/reject and final timestamps
- [ ] JSON export with intervals and provenance
- [x] Real detector measured on a public test set (or documented blocker) — VideoJev-4B on held-out long videos (S3-17, 2026-11-22: recall 0.86 cooking / 0.47 driving vs 0.85 target, not met or not confirmed; Charades-STA is reference only)
- [ ] Alpha deck ready for upload by 2026-11-30 23:59
- [ ] Limitations explicit; no fabricated metrics

## 4. Dependencies and blockers

| Dependency | Owner | Needed by |
|---|---|---|
| Client answers: privacy, reviewer, dataset meaning, JSON fields | Product Owner | 2026-11-17 |
| Privacy approval for Gemini (only if verify is turned on; not needed for the self-hosted detector) | Backend owner | 2026-11-18 |
| Compute decision (12 GB laptop / GPU / API); VideoJev-4B already runs on an 8 GB laptop with offload, slowly | Architect + supervisors | 2026-11-19 |
| Team capacity and roles | Scrum Master | 2026-11-16 |
| Official guidelines files (401 wall) | Team member with AAI | 2026-11-16 |
| Customer's OpenLABEL example | Product Owner | 2026-11-18 |

## 5. Notes

- Mock stays the CI default even with the `videojev` adapter integrated: tests must run without network or GPU.
- Every delivered PDF must be generated from repository Markdown (Sprint 2 retro action A-6).
- Do not start optional features (summaries, semantic search, multi-model UI) before the Alpha gate.
