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
until the frontend switches over (see §3). The auth/dataset code described here is **already merged**; the
Search/SearchVideo layer is **not yet implemented** (see §4).

---

## 1. Entity & Table Mapping

| Current (as-built / current code) | Target | Notes |
|---|---|---|
| `projects` | `datasets` | `datasets` exists **now** (`backend/app/models.py:428-442`): `id`, `name String(200)`, `description Text default ""`, `created_by_id FK users.id SET NULL`, timestamps. **`description` is still present** — the "name only / description removed" phrasing from Design v1.2 §4.3 is not yet reflected in code; `use_case` never existed in code. `created_by` is `created_by_id` (FK to `users.id`, nullable). The `projects` table itself remains untouched during the transition. |
| `action_definitions` | `searches.prompt` (+ optional `searches.title`) | No more pre-defined actions. Each search carries its own free-text prompt; an optional `title` labels the search — per v1.2, `Search.title` is a *short automatic title generated for long prompts*. **Not implemented yet** (no `Search` model/table). |
| `processing_jobs` with `kind="candidate_proposal"` | split into parent **`searches`** + child **`search_videos`** | 1 `searches` row per prompt run across a dataset; 1 `search_videos` row per video in that search, linking `search_id`, `video_id`, and `job_id -> processing_jobs.id`. Per-video `processing_jobs` rows remain the worker queue (kind `candidate_proposal`, `backend/app/models.py:100-102`). **Not implemented yet.** |
| `videos.project_id` | `videos.dataset_id` | Nullable during the transition. A video belongs to exactly one dataset. **Not implemented yet** (no `dataset_id` column on `videos`). |
| `candidates.job_id` | `candidates.search_id` | Nullable during the transition; kept **alongside** `job_id` until cutover. **Not implemented yet.** |
| — (new, **implemented**) | `dataset_memberships` | Actual table is **`dataset_memberships`** (`backend/app/models.py:445-460`), *not* `dataset_assignments`: `id`, `dataset_id FK datasets CASCADE`, `user_id FK users CASCADE`, `created_at`; `UniqueConstraint(dataset_id, user_id)` named `uq_dataset_membership`. **No `assigned_by` / `assigned_at` columns** — those fields were dropped in favour of the `users` table (`created_by_id` on `datasets` carries the ownership notion). |
| — (new, **implemented**) | `users`, `user_sessions`, `invitations` | Full auth model is in place: `User` (`backend/app/models.py:375`, global `role`), `UserSession` (token-hash sessions), `Invitation` (email invitations). See §3. |

Additional notes:

- **`search_videos`** will carry at minimum `search_id`, `video_id`, `job_id` (FK to `processing_jobs.id`),
  one row per (search, video). The search's aggregate status is derived from these rows' jobs (see §2). Per v1.2
  (§4.3/§4.4/§6.2.1) it also enables: **adding videos to a dataset that has searches runs those searches on the
  new videos after confirmation**.
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
| `POST` | `/api/v1/datasets` | `create_dataset` (`backend/app/api/datasets.py:54`) — `require_roles(administrator, dataset_admin)`; body `DatasetCreate{name, description}`; sets `created_by_id=principal.user.id`; auto-adds a `dataset_admin` creator to `dataset_memberships`. |
| `GET` | `/api/v1/datasets` | `list_datasets` (datasets.py:78) — administrator sees all; everyone else sees only datasets they are a member of. |
| `GET` | `/api/v1/datasets/{dataset_id}` | `get_dataset` (datasets.py:90) — `_require_access` (admin sees all, else membership required, 404 to hide existence). |
| `GET` | `/api/v1/datasets/{dataset_id}/members` | `list_members` (datasets.py:101) — returns `DatasetMemberOut{user_id, email, full_name, role, created_at}`. |
| `POST` | `/api/v1/datasets/{dataset_id}/members` | `add_member` (datasets.py:127) — `require_roles(administrator, dataset_admin)`; body `DatasetMemberAdd{user_id? , email?}`; dataset_admin may add **annotators only** (403 otherwise); 409 `MEMBER_EXISTS`. |

**There is no `DELETE /datasets/{id}/members/{user_id}` and no `PUT /users/{user_id}/assignments`** — membership
is currently add/list only. Those are future work, not present.

### To be implemented (target mapping)

| Current endpoint | New endpoint | Notes |
|---|---|---|
| `POST /api/v1/projects` | `POST /api/v1/datasets` | Already implemented (see above). |
| `GET /api/v1/projects` | `GET /api/v1/datasets` | Already implemented (see above). |
| `GET /api/v1/projects/{project_id}` | `GET /api/v1/datasets/{dataset_id}` | Already implemented (see above). |
| `POST /api/v1/projects/{project_id}/videos` | `POST /api/v1/datasets/{dataset_id}/videos` | Multipart upload; probe/checksum/range-streaming behaviour reused as-is. |
| `GET /api/v1/projects/{project_id}/videos` | `GET /api/v1/datasets/{dataset_id}/videos` | |
| `POST /api/v1/projects/{project_id}/actions/{action_id}/jobs` | `POST /api/v1/datasets/{dataset_id}/searches` | Body carries a free-text `prompt` (plus optional `title`) instead of `action_id`. Creates 1 `searches` row + 1 `search_videos` row + 1 `processing_jobs` job per ready video; returns `202` with the search id. Keep existing `Idempotency-Key` semantics (per video, `<key>:<video_id>`). |
| `GET /api/v1/jobs/{job_id}` | `GET /api/v1/searches/{search_id}` | Status **aggregated across all `search_videos`**: `queued → running → done`, or `failed` with per-video partial results (per [DESIGN_DESCRIPTION.md §7](DESIGN_DESCRIPTION.md)). |
| `POST/GET /api/v1/projects/{project_id}/exports` | `POST/GET /api/v1/datasets/{dataset_id}/exports` (and optionally `.../searches/{search_id}/exports`) | **Exports mapping (currently missing).** The `dataset_exports` table is still **project-scoped** (`project_id FK projects.id CASCADE`, `backend/app/models.py:346-367`) despite its name. Target model scopes exports to `dataset_id` + optional `search_id` — the "dataset" column is the migration gap, matching `videos.dataset_id`. See §4 item 4. |
| `GET/DELETE /api/v1/exports/{export_id}`, `GET /api/v1/exports/{export_id}/download` | unchanged paths, but re-scoped to dataset access control | Export detail/download stay id-based; their *authorization* must become dataset-scoped (`_require_access`) rather than project-scoped. |

Assignment endpoints (target, replacing the old header-based identity — see §3):

| Method | Endpoint | Notes |
|---|---|---|
| `POST` | `/api/v1/datasets/{dataset_id}/members` | **Implemented** — the grant mechanism (matches the v1.2 "assign users from the dataset or from the user" model). |
| `DELETE` | `/api/v1/datasets/{dataset_id}/members/{user_id}` | **Not implemented** — future revoke endpoint (natural fit for `uq_dataset_membership`). |
| `PUT` | `/api/v1/users/{user_id}/assignments` | **Not implemented** — future bulk-replace of a user's dataset set. |

---

## 3. Transition & Coexistence Plan

- **Legacy stays untouched.** `projects`, `action_definitions`, `processing_jobs` and every existing `/api/v1`
  project/action/job endpoint keep working exactly as today. **All existing backend tests continue passing
  unchanged.** Nothing is renamed, dropped, or re-pointed until the team switches the frontend over.
- **Additive schema only.** New tables (`users`, `invitations`, `user_sessions`, `datasets`, `dataset_memberships`
  — already added) and future tables (`searches`, `search_videos`) plus new nullable columns
  (`videos.dataset_id`, `candidates.search_id`) are added alongside the old ones. Old columns
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
- **Dataset scoping**: `_require_access(session, principal, dataset)` (`backend/app/api/datasets.py:44-51`) —
  administrators see everything; everyone else needs a `DatasetMembership`, and non-members get **404** (not 403)
  to avoid revealing a dataset's existence.
- The static `require_token` middleware (`backend/app/deps.py:38-51`, keyed to `VLM_API_TOKEN`) still guards the
  legacy project/video/job/candidate/export routes and is **independent** of the new session auth.

### Cutover (later, out of scope here)

Frontend moves to the new endpoints → backfill `dataset_id` / `search_id` from the legacy columns → drop legacy
tables, columns and routes. Decide the `/api/v1` vs `/api/v2` question first (see §4 item 2).

---

## 4. Current state & discrepancies noticed in this plan

1. **"56 tests" is a Sprint-2 number.** [API_CONTRACTS.md](API_CONTRACTS.md) §9 says "56 tests at Sprint 2 close",
   but `backend/tests/` defines 72 `def test_` functions across 9 files, and [DESIGN_DESCRIPTION.md §4](DESIGN_DESCRIPTION.md)
   claims "80 backend + 21 UI". Recommend "the entire existing backend suite passes unchanged" and confirm the exact
   collected count with `pytest backend/tests`.
2. **`/api/v1` was declared frozen.** [API_CONTRACTS.md §8](API_CONTRACTS.md) records that during migration `/api/v1`
   is frozen and the new contract goes behind `/api/v2` (or `/api` with a version header) — "Decide in Sprint 3".
   The new dataset/auth routes are currently mounted under `/api/v1` (additive, non-breaking), which contradicts
   that recorded plan unless the team explicitly decides to extend `/api/v1`.
3. **`dataset_assignments` → `dataset_memberships`.** The plan's target table name is wrong: the merged code uses
   `dataset_memberships` (`backend/app/models.py:445`) with no `assigned_by`/`assigned_at`; ownership is expressed
   by `datasets.created_by_id`. The `assigned_by`/`assigned_at` audit fields were dropped.
4. **Exports are still project-scoped.** `dataset_exports` keeps `project_id FK projects.id` (`backend/app/models.py:346-367`);
   no dataset/search scoping exists in code or in `backend/app/api/exports.py`. The target is `dataset_id` +
   optional `search_id` — this is the one mapping row that was missing and is now documented in §2.
5. **"Datasets are name-only" is not yet true in code.** `Dataset.description` exists (`backend/app/models.py:435`)
   and `DatasetCreate` accepts it (`backend/app/schemas.py:332-334`). Design v1.2 §4.3 removes `description`, but the
   merged code has not dropped it. `use_case` never existed in code. Flag this when the schema is next revised.
6. **Search/SearchVideo are not implemented.** No `Search`/`SearchVideo` model, table, or router exists yet
   (grep across `backend/**/*.py` found nothing); the only hits are a stale docstring and a test helper name. The
   "split into `searches` + `search_videos`" rows in §1 are target design, not current code.
7. **Identity default changed.** The old `annotations.reviewer` column still defaults to `"anonymous"`
   (`backend/app/models.py:329`) and remains a plain `String(100)`, but all *new* tables use integer FKs to `users.id`.
   The two schemes coexist during transition; the `String(100)` reviewer column is legacy-only and should not be
   used as a pattern for new tables.
