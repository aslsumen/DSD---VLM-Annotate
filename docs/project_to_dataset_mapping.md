# Projects/Jobs → Datasets/Searches — Migration Mapping

**Purpose.** Single reference for migrating the backend domain from the single-project/single-job model
(`projects` / `action_definitions` / `processing_jobs`) to **Dataset, DatasetMembership, Search, SearchVideo**.
Written before any backend migration code so the whole team migrates from the same picture.

**Sources.** `VLM_Annotate_Design_Description_v1.2.docx` (design doc), [API_CONTRACTS.md](API_CONTRACTS.md),
[DATABASE_SCHEMA.md](DATABASE_SCHEMA.md), [as-built/IMPLEMENTED_BASELINE_2026-11-05.md](as-built/IMPLEMENTED_BASELINE_2026-11-05.md),
and the current code in `backend/app/` (models, routers, dependencies, Alembic migrations) — cited inline.
*(Verification note: the docx body after the table of contents could not be parsed in the authoring environment;
the v1.2 changes below were verified from the document's own Changelog table — entry 1.2, 2026-11-15 — and the
code facts are from the repository as of 2026-11-19/20, after the PR #48 session-auth/dataset-scoping merge.)*

**Status.** Planning reference. Legacy `projects`, `action_definitions` and `processing_jobs` stay untouched
until the frontend switches over (see §3). The auth/dataset layer was merged in PR #48, and the
Search/SearchVideo layer (models, migration, fan-out, worker sync and read endpoints) is **implemented as of
2026-11-20** — see §2 and §4 item 6 for the as-built details. The frontend has not switched over yet.

---

## 1. Entity & Table Mapping

| Current (as-built / current code) | Target | Notes |
|---|---|---|
| `projects` | `datasets` | `datasets` exists **now** (`backend/app/models.py:456-470`): `id`, `name String(200)`, `description Text default ""`, `created_by_id FK users.id SET NULL`, timestamps. **`description` is still present** — the "name only / description removed" phrasing from Design v1.2 §4.3 is not yet reflected in code; `use_case` never existed in code. `created_by` is `created_by_id` (FK to `users.id`, nullable). The `projects` table itself remains untouched during the transition. |
| `action_definitions` | `searches.prompt` (+ optional `searches.title`) | No more pre-defined actions. Each search carries its own free-text prompt; an optional `title` labels the search — per v1.2, `Search.title` is a *short automatic title generated for long prompts*. **Implemented** — `Search` (`backend/app/models.py:491-525`), migration `e5b9c3d7a2f1`; `title` is auto-derived (first ~60 chars, trimmed) when omitted (`backend/app/api/searches.py:_auto_title`). |
| `processing_jobs` with `kind="candidate_proposal"` | split into parent **`searches`** + child **`search_videos`** | **Implemented.** 1 `searches` row per prompt run across a dataset; 1 `search_videos` row per video in that search, linking `search_id`, `video_id`, and `job_id -> processing_jobs.id` with `UniqueConstraint(search_id, video_id)` (`backend/app/models.py:528-551`, migration `e5b9c3d7a2f1`). Per-video `processing_jobs` rows remain the worker queue (kind `candidate_proposal`, `backend/app/models.py:100-102`); `SearchVideo.status` is synchronised by the worker and the parent `Search.status` is recomputed from those rows. |
| `videos.project_id` | `videos.dataset_id` | **Implemented (nullable).** `Video.project_id` is now nullable and `Video.dataset_id` exists (`backend/app/models.py:198-204`, migration `e5b9c3d7a2f1`). A video belongs to exactly one dataset; both columns coexist during the transition. `ProcessingJob.project_id` was also relaxed to nullable so dataset search jobs can run with no project (migration `c9f0d3a1b2e4`). |
| `candidates.job_id` | `candidates.search_id` | **Implemented (nullable).** `Candidate.search_id` is added alongside `job_id` (`backend/app/models.py:290-292`, migration `e5b9c3d7a2f1`); search fan-out sets it at candidate creation. `job_id` stays populated until cutover. |
| — (new, **implemented**) | `dataset_memberships` | Actual table is **`dataset_memberships`** (`backend/app/models.py:473-488`), *not* `dataset_assignments`: `id`, `dataset_id FK datasets CASCADE`, `user_id FK users CASCADE`, `created_at`; `UniqueConstraint(dataset_id, user_id)` named `uq_dataset_membership`. **No `assigned_by` / `assigned_at` columns** — those fields were dropped in favour of the `users` table (`created_by_id` on `datasets` carries the ownership notion). |
| — (new, **implemented**) | `users`, `user_sessions`, `invitations` | Full auth model is in place: `User` (`backend/app/models.py:396`, global `role`), `UserSession` (token-hash sessions), `Invitation` (email invitations). See §3. |

Additional notes:

- **`search_videos`** carries `search_id`, `video_id`, `job_id` (FK to `processing_jobs.id`), `status` and
  `error_message`, one row per (search, video) with a unique constraint. The search's aggregate status is derived
  from those rows (see §2). Per v1.2 (§4.3/§4.4/§6.2.1) it also enables: **adding videos to a dataset that has
  searches runs those searches on the new videos after confirmation** — the "re-run on new videos" behaviour is
  *not* implemented yet; only the data model supports it.
- **`candidates.action_id`** is superseded by `candidates.search_id` (the prompt lives on the search); treat it
  like `job_id` — kept during transition, dropped after cutover.
- **Identity is real users now, not string identifiers.** `user_id` / `created_by_id` are FKs to `users.id`
  (int). There is no `annotations.reviewer`-style `String(100)` fallback for the new tables — that assumption is
  obsolete (see §3 and §4 item 5).
- All schema changes are **additive**: the as-built columns documented in
  [IMPLEMENTED_BASELINE §2](as-built/IMPLEMENTED_BASELINE_2026-11-05.md) keep working unchanged.

---

## 2. Endpoint Mapping (`/api/v1/...`)

### Already implemented (current code)

| Method | Endpoint | Notes |
|---|---|---|
| `POST` | `/api/v1/datasets` | `create_dataset` (`backend/app/api/datasets.py:68`) — `require_roles(administrator, dataset_admin)`; body `DatasetCreate{name, description}`; sets `created_by_id=principal.user.id`; auto-adds a `dataset_admin` creator to `dataset_memberships`. |
| `GET` | `/api/v1/datasets` | `list_datasets` (datasets.py:92) — administrator sees all; everyone else sees only datasets they are a member of. |
| `GET` | `/api/v1/datasets/{dataset_id}` | `get_dataset` (datasets.py:104) — `_require_access` (admin sees all, else membership required, 404 to hide existence). |
| `GET` | `/api/v1/datasets/{dataset_id}/members` | `list_members` (datasets.py:115) — returns `DatasetMemberOut{user_id, email, full_name, role, created_at}`. |
| `POST` | `/api/v1/datasets/{dataset_id}/members` | `add_member` (datasets.py:145) — `require_roles(administrator, dataset_admin)`; body `DatasetMemberAdd{user_id? , email?}`; dataset_admin may add **annotators only** (403 otherwise); 409 `MEMBER_EXISTS`. |
| `POST` | `/api/v1/datasets/{dataset_id}/videos` | `upload_dataset_video` (`backend/app/api/datasets.py:188-215`) — **implemented**; `require_roles(administrator, dataset_admin)` + `_require_access`; shares `ingest_video` with the legacy project upload; stores under `videos/dataset-{id}`, sets `dataset_id`, leaves `project_id=None`. |
| `GET` | `/api/v1/datasets/{dataset_id}/videos` | `list_dataset_videos` (`backend/app/api/datasets.py:218-230`) — **implemented**; `get_current_principal` + `_require_access`; newest first. |
| `POST` | `/api/v1/datasets/{dataset_id}/searches` | `create_search` (`backend/app/api/searches.py:249-370`) — **implemented**; `202`; body `SearchCreate{prompt, title?, video_ids?, adapter_name?, params?}`; creates 1 `Search` + 1 `SearchVideo` + 1 `ProcessingJob` per ready video; unknown/unready ids → `422 VIDEOS_NOT_IN_DATASET`; optional `Idempotency-Key` header (≤100 chars) replays the existing search instead of fanning out again, and a changed request with the same key → `409 IDEMPOTENCY_KEY_REUSED` with `details.mismatched_fields`. The request is recorded in `searches.request_scope_json` and future replays compare against that snapshot, never against the live `search_videos` rows. |
| `GET` | `/api/v1/datasets/{dataset_id}/searches` | `list_searches` (`backend/app/api/searches.py:373-399`) — **implemented**; `list[SearchOut]`, newest first, filters `status` (enum), `limit` (1…500, default 100) and `offset`; per-status counts come from one aggregate query. Used by the UI to restore the search list on reload. |
| `GET` | `/api/v1/searches/{search_id}` | `get_search` (`backend/app/api/searches.py:401-409`) — **implemented**; returns `SearchDetailOut` with `status`, the five per-status counts and the `SearchVideo` list. |
| `POST` | `/api/v1/datasets/{dataset_id}/searches/{search_id}/cancel` | `cancel_search` (`backend/app/api/searches.py:411-459`) — **implemented 2026-11-26**; `200`; `require_roles(administrator, dataset_admin)` + `_require_search_access`; cancels every queued/running video through `cancel_job`, so the per-video rows and the aggregate settle as usual; a search that is already settled is returned unchanged instead of failing (the frontend retries this on a flaky connection). |
| `POST` | `/api/v1/datasets/{dataset_id}/searches/{search_id}/retry` | `retry_search` (`backend/app/api/searches.py:461-539`) — **implemented 2026-11-26**; `202`; same role/access guards; re-queues only the failed videos (fresh `ProcessingJob` per video, prompt/params/adapter replayed from the stored request scope); `409 SEARCH_NOT_RETRYABLE` when there is nothing failed to retry. |
| `GET` | `/api/v1/searches/{search_id}/candidates` | `list_search_candidates` (`backend/app/api/searches.py:541-570`) — **implemented**; optional `review_state` / `verdict` / `limit` filters, combinable (`annotations` is joined at most once, so `review_state` + `verdict` together no longer errors). |

**There is no `DELETE /datasets/{id}/members/{user_id}` and no `PUT /users/{user_id}/assignments`** — membership
is currently add/list only. Those are future work, not present.

### Project → dataset migration status

| Current endpoint | New endpoint | Notes |
|---|---|---|
| `POST /api/v1/projects` | `POST /api/v1/datasets` | Already implemented (see above). |
| `GET /api/v1/projects` | `GET /api/v1/datasets` | Already implemented (see above). |
| `GET /api/v1/projects/{project_id}` | `GET /api/v1/datasets/{dataset_id}` | Already implemented (see above). |
| `POST /api/v1/projects/{project_id}/videos` | `POST /api/v1/datasets/{dataset_id}/videos` | **Implemented** (`upload_dataset_video`, datasets.py:188). Multipart upload; probe/checksum/range-streaming behaviour reused via the shared `ingest_video` helper. |
| `GET /api/v1/projects/{project_id}/videos` | `GET /api/v1/datasets/{dataset_id}/videos` | **Implemented** (`list_dataset_videos`, datasets.py:218). |
| `POST /api/v1/projects/{project_id}/actions/{action_id}/jobs` | `POST /api/v1/datasets/{dataset_id}/searches` | **Implemented** (`create_search`, searches.py:249). Body carries a free-text `prompt` (plus optional `title`) instead of `action_id`. Creates 1 `searches` row + 1 `search_videos` row + 1 `processing_jobs` job per ready video; returns `202` with the search and its per-video breakdown. Also accepts an `Idempotency-Key` header, stored globally unique on `searches.idempotency_key` (not suffixed per video, unlike the legacy batch route); the request itself is snapshotted in `searches.request_scope_json` so an identical replay keeps working even after the videos it named are deleted. |
| `GET /api/v1/jobs/{job_id}` | `GET /api/v1/searches/{search_id}` | **Implemented** (`get_search`, searches.py:401). Status **aggregated across all `search_videos`**: `queued → running → done`, `failed` when every video failed, `partial` when some succeeded and some failed; per-video results are returned in the `videos` list. |
| `GET /api/v1/jobs` (filtered list) | `GET /api/v1/datasets/{dataset_id}/searches` | **Implemented** (`list_searches`, searches.py:373). Filters `status` + `limit`/`offset` paging; returns `SearchOut[]` (counts, no per-video list). |
| `POST /api/v1/jobs/{job_id}/cancel` (per job) | `POST /api/v1/datasets/{dataset_id}/searches/{search_id}/cancel` | **Implemented 2026-11-26** (`cancel_search`, searches.py:411). One call cancels every queued/running video of the search; the per-job route survives for legacy project work. Idempotent: a settled search is returned with `200` rather than an error. |
| retry a failed job | `POST /api/v1/datasets/{dataset_id}/searches/{search_id}/retry` | **Implemented 2026-11-26** (`retry_search`, searches.py:461). `202`; re-queues only the failed videos with a fresh job per video, replaying the stored prompt/params/adapter; `409 SEARCH_NOT_RETRYABLE` when nothing failed. |
| `POST/GET /api/v1/projects/{project_id}/exports` | `POST/GET /api/v1/datasets/{dataset_id}/exports` (and optionally `.../searches/{search_id}/exports`) | **Exports mapping (currently missing).** The `dataset_exports` table is still **project-scoped** (`project_id FK projects.id CASCADE`, `backend/app/models.py:367-393`) despite its name. Target model scopes exports to `dataset_id` + optional `search_id` — the "dataset" column is the migration gap, matching `videos.dataset_id`. See §4 item 4. |
| `GET/DELETE /api/v1/exports/{export_id}`, `GET /api/v1/exports/{export_id}/download` | unchanged paths, but re-scoped to dataset access control | Export detail/download stay id-based; their *authorization* must become dataset-scoped (`_require_access`) rather than project-scoped. |

Assignment endpoints (target, replacing the old header-based identity — see §3):

| Method | Endpoint | Notes |
|---|---|---|
| `POST` | `/api/v1/datasets/{dataset_id}/members` | **Implemented** — `add_member` (datasets.py:145); the grant mechanism (matches the v1.2 "assign users from the dataset or from the user" model). |
| `DELETE` | `/api/v1/datasets/{dataset_id}/members/{user_id}` | **Not implemented** — future revoke endpoint (natural fit for `uq_dataset_membership`). |
| `PUT` | `/api/v1/users/{user_id}/assignments` | **Not implemented** — future bulk-replace of a user's dataset set. |

---

## 3. Transition & Coexistence Plan

- **Legacy stays untouched.** `projects`, `action_definitions`, `processing_jobs` and every existing `/api/v1`
  project/action/job endpoint keep working exactly as today. **All existing backend tests continue passing
  unchanged.** Nothing is renamed, dropped, or re-pointed until the team switches the frontend over.
- **Additive schema only.** New tables (`users`, `invitations`, `user_sessions`, `datasets`, `dataset_memberships`,
  `searches`, `search_videos`) plus new nullable columns (`videos.dataset_id`, `candidates.search_id`) were added
  alongside the old ones via migrations `d03f1c4ffd30`, `e5b9c3d7a2f1`, `c9f0d3a1b2e4` and
  `f1a4b8c2d6e9` (the last one adds the nullable, unique `searches.idempotency_key`). Old columns
  (`videos.project_id`, `candidates.job_id`, `candidates.action_id`) remain populated and valid until cutover.
- **Job mechanics are reused, not replaced.** `processing_jobs` remains the worker queue: each search's per-video
  work is still one `processing_jobs` row (kind `candidate_proposal`) with the existing claim/retry/cancel/
  idempotency semantics; `search_videos.job_id` merely adds the search-level view on top. Nothing in the worker
  contract changes.
- **Dual read paths during the window.** Old endpoints read old tables; new endpoints read new tables. No endpoint
  reads both, so the two worlds cannot corrupt each other; the only shared rows are the transition columns above.

### Session authentication & dataset scoping (current, replaces the old header scheme)

The previous `X-User-Id` / `X-User-Role` header assumption is **obsolete**. Real auth landed in PR #48:

- **Identity is a bearer session token**, resolved by `get_current_principal`
  (`backend/app/deps.py:82-119`): `Authorization: Bearer <token>` → `hash_token(token)` lookup in `UserSession`
  → valid (not revoked, not expired) → `Principal(user=User, role=user.role, is_authenticated=True)`.
- **`User.role` is global** (`backend/app/models.py:128-133`, enum `administrator | dataset_admin | annotator`) —
  it is **never per-dataset**; dataset visibility is governed by `dataset_memberships`, not by role.
- **Auth is opt-in by default**: `Settings.auth_required: bool = False` (`backend/app/config.py`). When a token is
  absent and auth is not required, `get_current_principal` returns a **synthetic**
  `Principal(user=None, role=administrator, is_authenticated=False)` so the local demo keeps working.
- **Role gate**: `require_roles(*allowed)` (`backend/app/deps.py:122-137`) — administrator always passes, other
  roles must be listed.
- **Dataset scoping**: `_require_access(session, principal, dataset)` (`backend/app/api/datasets.py:57-64`) —
  administrators see everything; everyone else needs a `DatasetMembership`, and non-members get **404** (not 403)
  to avoid revealing a dataset's existence.
- **The shared legacy routes follow the same rules since 2026-11-25.** `app/access.py` resolves the dataset that
  owns a by-id row (`dataset_for_video` / `dataset_for_job` / `dataset_for_candidate`) and applies
  `401` (anonymous) → `404` (non-member) → `403` (member without the write role), in that order and **inside the
  handler**, so existence never leaks. Handlers take `get_optional_principal` (`backend/app/deps.py:162-187`)
  instead of a required dependency precisely because the same routes still serve project-owned rows, which were
  never authenticated; `GET /jobs` filters rather than refusing. Annotating needs membership only. Covered by
  `backend/tests/test_dataset_authz.py` (9 tests).
- **Job / `search_videos` / `searches` write atomicity (2026-11-25).** Job execution keeps the three levels in step:
  `execute_job` fences the job's ownership before its first child write, every write path (`_finish`,
  `_record_failure`, `fail_job_now`, `retry_job`, `reap_stale_jobs`, `cancel_job`) commits the job row and its
  `SearchVideo` mirror in one transaction and only then derives the aggregate via `_settle_search_status`, and the
  worker runs `reconcile_search_state` (`backend/app/services/pipeline.py:951`) every tick to repaint a drifted
  `SearchVideo` from its job and settle any `Search` whose videos are all done. Four regression tests in section 7 of
  `backend/tests/test_searches.py`.
- **Video deletion is one transaction with its search settle (2026-11-25).** `DELETE /api/v1/videos/{id}` calls
  `refresh_searches_for_video(..., commit=False)`, deletes the `Video` row and commits, then converges the affected
  Searches through `settle_searches` (after the commit on purpose: the derivation must see a peer worker's row) and
  only then removes stored files. `Video.jobs` declares `passive_deletes=True`, so the foreign-key cascade takes the
  video's `processing_jobs` and `candidates` with it instead of nulling `processing_jobs.video_id` and leaving an
  ownerless `running` job; `execute_job` catches `SQLAlchemyError`, rolls back, re-reads the job and either returns
  (row gone or taken over) or fails it cleanly. Three regression tests in section 8 of `backend/tests/test_searches.py`.
- The static `require_token` middleware (`backend/app/deps.py:38-51`, keyed to `VLM_API_TOKEN`) still guards the
  legacy project/video/job/candidate/export routes and is **independent** of the new session auth.

### Cutover (later, out of scope here)

Frontend moves to the new endpoints → backfill `dataset_id` / `search_id` from the legacy columns → drop legacy
tables, columns and routes. The `/api/v1` vs `/api/v2` question is settled: the team extends `/api/v1` additively
(see §4 item 2).

---

## 4. Current state & discrepancies noticed in this plan

1. **"56 tests" is a Sprint-2 number.** [API_CONTRACTS.md](API_CONTRACTS.md) §9 says "56 tests at Sprint 2 close".
   That figure was correct when written and is no longer: as of 2026-11-26 `backend/tests/` defines **154
   `def test_` functions across 15 files**, and pytest reports **162 collected** (two of the functions are
   parametrised and expand to 6 and 4 cases). All 162 pass on Windows. Quote the number pytest prints.
2. **`/api/v1` was declared frozen — now resolved.** [API_CONTRACTS.md §8](API_CONTRACTS.md) used to say `/api/v1`
   is frozen and the new contract goes behind `/api/v2`. On 2026-11-20 the team decided to extend `/api/v1`
   additively instead (the new dataset/auth/search routes are new paths; no frozen endpoint changes), and
   API_CONTRACTS.md §8/§9 were updated to record that. Superseded — no action needed.
3. **`dataset_assignments` → `dataset_memberships`.** The plan's target table name is wrong: the merged code uses
   `dataset_memberships` (`backend/app/models.py:473`) with no `assigned_by`/`assigned_at`; ownership is expressed
   by `datasets.created_by_id`. The `assigned_by`/`assigned_at` audit fields were dropped.
4. **Exports are still project-scoped.** `dataset_exports` keeps `project_id FK projects.id` (`backend/app/models.py:367-393`);
   no dataset/search scoping exists in code or in `backend/app/api/exports.py`. The target is `dataset_id` +
   optional `search_id` — this is the one mapping row that was missing and is now documented in §2.
5. **"Datasets are name-only" is not yet true in code.** `Dataset.description` exists (`backend/app/models.py:456`)
   and `DatasetCreate` accepts it (`backend/app/schemas.py:336`). Design v1.2 §4.3 removes `description`, but the
   merged code has not dropped it. `use_case` never existed in code. Flag this when the schema is next revised.
6. **Search/SearchVideo are now implemented.** `Search`/`SearchVideo` models and tables exist
   (`backend/app/models.py:491-551` plus `request_scope_json` at `:525`, migrations `e5b9c3d7a2f1`,
   `f1a4b8c2d6e9` and `b8d2e5a4c9f3`), with fan-out and read endpoints in `backend/app/api/searches.py` and
   worker synchronisation in `backend/app/services/pipeline.py`. Automated tests were added 2026-11-21,
   extended 2026-11-24, 2026-11-25 and 2026-11-26 in `backend/tests/test_searches.py` (51 tests: fan-out,
   status aggregation, role + dataset scoping, dataset search listing, `Idempotency-Key`, job-lifecycle sync on
   cancel / reaper / retry / video delete, concurrent completion, the job / `SearchVideo` / `Search` consistency
   tests with the `reconcile_search_state` sweep, the video-deletion atomicity + job cascade tests, and the
   idempotency request-scope + search cancel/restart tests), plus `backend/tests/test_review_filters.py`
   (3 tests) for the `review_state` + `verdict` combination. Not done yet: the "re-run searches on newly added
   videos" behaviour from v1.2 and dataset-scoped exports. Dataset authorization on the shared legacy routes is
   covered by
   `backend/tests/test_dataset_authz.py` (9 tests) — see §3.
7. **Deleting a video takes its job history with it.** `Video.jobs` now declares `passive_deletes=True`
   (`backend/app/models.py:220-227`), so the `ondelete="CASCADE"` in `processing_jobs.video_id` actually fires and a
   deleted video's jobs and candidates disappear. That is the DDL's original intent, and it is why
   `dataset_for_job`'s search-video/candidate fallbacks now only cover rows an older build left behind (it used to
   null the foreign key instead). Decide before Sprint 4 whether that history must be retained for auditing — if so,
   the cascade has to become an explicit soft delete, which is a migration, not an ORM option.
8. **Identity default changed.** The old `annotations.reviewer` column still defaults to `"anonymous"`
   (`backend/app/models.py:358`) and remains a plain `String(100)`, but all *new* tables use integer FKs to `users.id`.
   The two schemes coexist during transition; the `String(100)` reviewer column is legacy-only and should not be
   used as a pattern for new tables.
