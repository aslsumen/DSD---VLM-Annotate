# Implementation Log

Chronological record of what was actually built, changed and measured. Newest last.

## 2026-11-26 — Idempotency request scope, and search-level cancel / restart

**Goal:** an `Idempotency-Key` replay was judged against mutable state instead of the request that created the
search. Reported from PR review with three reproductions:

- The same key with **different `params`** replayed the old search instead of returning `409` — `params` was never
  compared at all.
- Switching between an **explicit `video_ids` subset and the whole dataset** (either direction) also replayed,
  because the rule short-circuited "omitted `video_ids`" to a match.
- **Deleting a selected video** made an identical replay of the original explicit subset return `409`: the video
  scope was read from the live `search_videos` rows, which the delete removes.

Same review also asked for clear **cancel / restart semantics** on a search, as a frontend-cutover dependency.

**Code**

- `app/models.py` `Search.request_scope_json` (`Text`, NOT NULL, default `"{}"`): canonical JSON snapshot of the
  request — `dataset_id`, `prompt`, `params`, `adapter_name` (stored resolved, so omitting it equals naming the
  configured default) and the requested `video_ids` (`null` when the caller omitted them). Migration
  `b8d2e5a4c9f3_search_request_scope.py` adds the column with a `{}` server default so existing rows keep working,
  then drops the default.
- `app/api/searches.py`: `SCOPE_FIELDS` names the five fields that must match; `_request_scope` /
  `_dump_scope` (`sort_keys`, compact separators, so equal requests store equal text) / `_load_scope` /
  `_mismatched_fields` replace the old `_replay_matches`. `_replay_or_conflict` now raises
  `409 IDEMPOTENCY_KEY_REUSED` with `details.mismatched_fields`. Rows written before the column existed (`{}`) fall
  back to the old dataset + prompt comparison, with a logged warning.
- `create_search` builds the scope **before** resolving the adapter and the videos and stores it on the row, so a
  repeat still returns the original search after a video was deleted or an adapter was removed from the config.
- New `POST /api/v1/datasets/{dataset_id}/searches/{search_id}/cancel` (200) cancels every queued/running video via
  `cancel_job` and returns the settled search; a search that is already settled is returned unchanged, so the
  frontend can retry a cancel safely.
- New `POST /api/v1/datasets/{dataset_id}/searches/{search_id}/retry` (202) re-queues **only** the videos whose job
  failed, reusing `enqueue_candidate_job` with the failed job's adapter and params (falling back to the stored
  scope), and answers `409 SEARCH_NOT_RETRYABLE` when there is nothing to restart. Both endpoints require
  `dataset_admin` on a dataset the caller can access, and both keep exactly one writer per state.

**Matching contract**

| Field | Part of the match | Note |
|---|---|---|
| `dataset_id` | yes | a key is scoped to one dataset |
| `prompt` | yes | whitespace-stripped by the schema first |
| `params` | yes | exact canonical equality, no tolerance |
| `video_ids` | yes | compared as a set; `null` (= every ready video) is distinct from any subset |
| `adapter_name` | yes | stored resolved |
| `title` | no | presentation only |
| resolved video set | no | derived, and later uploads/deletes must not change the request identity |

**Tests:** `backend/tests/test_searches.py` section 9 — 16 tests: the reviewed local regression (create on one
video → delete it → replay the original request → same id, `total_videos` 0, `done`), params mismatch, subset→all
and all→subset, order/duplicate tolerance, title ignored, default adapter equivalence, adapter mismatch, a conflict
naming every mismatched field, the legacy `{}` fallback, search cancel across all videos, cancel idempotence, a
cancel that wins against a worker which already claimed the job, retry re-queueing only failures,
`SEARCH_NOT_RETRYABLE`, and the cancel/retry authorization matrix.

**No destructive change:** the column is additive and nullable-by-default at the SQL level for existing rows; no
table or column is dropped or renamed.

**Verification (actual):** `pytest -q` → **162 passed** and `ruff check --no-cache backend\app backend\tests` clean,
both run by the user on Windows on 2026-11-26. That matches the arithmetic: the suite holds 154 test functions over
15 files, two of them parametrised (6 and 4 cases), so `154 − 2 + 6 + 4 = 162` collected. Note that the suite does
**not** exercise migration `b8d2e5a4c9f3` — the fixtures build their schema with `Base.metadata.create_all` — so
applying it stays an explicit step:

```bash
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head    # c9f0d3a1b2e4 -> f1a4b8c2d6e9 -> b8d2e5a4c9f3
..\.venv\Scripts\python.exe -m pytest -q               # 162 passed
..\.venv\Scripts\python.exe -m ruff check app tests
```

## 2026-11-25 — Video deletion and its search settle in one transaction

**Goal:** `DELETE /api/v1/videos/{id}` could leave the database in a state no later run would repair. Reported from
PR review with two reproductions:

- A crash after `refresh_searches_for_video` returned but before the `Video` row was deleted left the video **and**
  its job in place while the search had already settled — with one video, `done` with zero videos. The settle
  committed (`_settle_search_status` commits by design so peers see the row), so the delete was no longer atomic with
  it.
- Deleting a video whose job was mid-run stranded the job. `Video.jobs` declared no `passive_deletes`, so SQLAlchemy
  loaded the children and **nulled** `processing_jobs.video_id` instead of letting the DDL cascade: the job survived
  with `video_id` *and* `project_id` NULL, the next candidate insert failed on its NOT NULL foreign keys, and the
  failed session then raised `PendingRollbackError` out of `execute_job`, leaving the job `running` for ever.

**Code**

- `app/services/pipeline.py`: `_settle_search_status(..., commit: bool = True)` and
  `refresh_searches_for_video(..., commit: bool = True)`. With `commit=False` the settle derives in place
  (`_recompute_search_status`) without committing or expiring, so a caller can own the whole transaction. New
  public `settle_searches(session, search_ids)` for the post-commit convergence pass, added to `__all__`.
- `app/api/videos.py` `delete_video`: `refresh_searches_for_video(..., commit=False)` → `session.delete(video)` →
  `session.commit()` → `settle_searches(...)` → storage cleanup. One transaction for the row removals, and the files
  are only touched after the commit, so a rolled-back delete never orphans a surviving row. The convergence pass
  runs afterwards on purpose: it must see a peer worker's committed row, which an in-transaction derivation cannot.
- `app/models.py` `Video.jobs`: `relationship(back_populates="video", passive_deletes=True)`, so the foreign-key
  cascade removes the jobs (and, through their own cascade, the candidates).
- `app/services/pipeline.py` `execute_job`: new `except SQLAlchemyError` branch placed before the generic handler.
  It captures `job_id`/`attempts`, rolls the poisoned session back, re-reads the row and returns quietly when the job
  is gone or was taken over; otherwise it fails the job through the normal path (`_record_failure` +
  `_commit_with_search_video`). A statement failure no longer escapes as `PendingRollbackError`.
- `app/access.py` `dataset_for_job`: docstring corrected — a delete now cascades instead of nulling, so the
  search-video/candidate fallbacks only cover rows left by older builds.

**Decision:** the job history of a deleted video goes with it. That is what the DDL (`ondelete="CASCADE"` on
`processing_jobs.video_id`) always intended, and the alternative — cancelling the jobs in the same transaction —
would keep `processing_jobs` rows whose video no longer exists, which is exactly the state that had no owner and no
dataset. The failing-job path above is what makes the cascade safe for a worker that is still running.

**No migration:** the fix is an ORM relationship option (the column and its `ON DELETE CASCADE` were already
migrated in `0001_initial_schema`) plus pure Python.

**Tests added** (section 8 of `backend/tests/test_searches.py`):

- `test_video_delete_rolls_back_with_its_search_settle` — monkeypatches `app.api.videos.refresh_searches_for_video`
  to run the real one with `commit=False` and then raise; after the session is gone the video, the job and the
  `SearchVideo` row are all still there and the search is not `done`; with the fault removed the same request
  succeeds and settles it.
- `test_deleting_a_video_mid_run_does_not_strand_the_job` — the adapter deletes its own video and then reports
  progress; `worker.run_once()` returns normally, no video/job/`SearchVideo`/`Candidate` row survives and the search
  is settled.
- `test_deleting_a_video_cascades_its_jobs_and_candidates` — after a successful run, deleting the video removes the
  job and its candidates and settles the search.
- `backend/tests/test_dataset_authz.py::test_job_whose_video_was_deleted_fails_closed` was rewritten: it used to
  reach the ownerless state by deleting the video, which now cascades. It builds the row with a raw
  `UPDATE ... video_id=None, project_id=None` instead, so the fail-closed rule is still pinned for rows an older
  build left behind.

**Verification (actual):** the suite was run on Windows after this change — **146 passed** — and held 138 test
functions at that point (three added in section 8 above, none removed; two of the 138 are parametrised, so
`138 − 2 + 6 + 4 = 146` collected). Later increments brought the suite to 162 — see the entry above. Run from
`backend/`: `python -m pytest -q` (146 passed at the time) and `python -m ruff check app tests`.

```bash
cd backend
..\.venv\Scripts\python.exe -m pytest -q          # 146 passed when this was written
..\.venv\Scripts\python.exe -m ruff check app tests
```

## 2026-11-25 — Job / SearchVideo / Search consistency across crashes and cancellation

**Goal:** the three levels could disagree, and each disagreement stranded a Search in a non-terminal state with
nothing left to finish it.

- A cancel or reclaim landing between `claim_next_job` and the start of `execute_job` was overwritten: the
  SearchVideo was painted `running` **before** any ownership check, so the row a cancel had just settled to
  `failed`/`"Job canceled"` was resurrected and the search hung in `running` forever.
- The job row and its SearchVideo mirror were committed in separate transactions everywhere except `cancel_job`:
  `_finish` and `_record_failure` committed the job alone, then the caller painted the row. A crash (or a
  `JobInterrupted` between them) left e.g. a `succeeded` job whose SearchVideo still said `running` — again a search
  that never finishes, and nothing recomputes it because no further event arrives.
- Rows written by older builds stayed wrong forever; nothing swept for drift.

**Code**

- `app/services/pipeline.py` `execute_job`: the first child write is now fenced. `_fence(session, job)` runs first,
  then the SearchVideo is set to `running` and committed, and only then is the aggregate settled; a `JobInterrupted`
  here rolls back, logs "no longer owned by this worker; not started" and returns the job untouched. A cancel that
  wins the race now stays won.
- `_finish` and `_record_failure` gained a keyword-only `commit: bool = True`; `execute_job` passes `commit=False`,
  paints the SearchVideo in the same transaction and commits once, then settles the search. The success,
  the three failure branches and the retry-requeue branch all follow that shape.
- New `_commit_with_search_video(session, job)`: commits the job's state and its SearchVideo mirror in **one**
  transaction, then derives the aggregate. `fail_job_now` and `retry_job` use it. The old
  `_sync_search_video_failure` helper is gone — its `commit()`-then-mirror shape was the bug.
- `_sync_search_video_status` is gone too: once every path inlined its repaint (`execute_job`,
  `reap_stale_jobs`, `cancel_job`) or used `_commit_with_search_video`, nothing called it. The module now has
  exactly one mirror writer per path, which is why `grep _sync_search_video` returns nothing.
- `reap_stale_jobs` and `cancel_job` now repaint the SearchVideo **inside** their existing transaction and settle the
  search only after the commit, so a peer session always sees the row before the aggregate is derived.
- New `reconcile_search_state(session) -> int` (exported): repaints any SearchVideo disagreeing with its job (the job
  is the source of truth; `canceled` maps to `failed` with `"Job canceled"`), and re-derives any Search still
  `queued`/`running`/`partial` whose videos have all settled. The drift predicate is computed in SQL, so an idle tick
  is one cheap query returning nothing. Idempotent: a second sweep returns 0. The return value counts **both** kinds
  of repair — repainted `SearchVideo` rows and `Search` aggregates that actually moved (`before` is read before the
  commit, then compared after `_settle_search_status`) — because a sweep that only settles a stale aggregate used to
  report 0, which reads as "consistent" to any caller that trusts the number.
- `app/worker.py` `run_once`: `reap_stale_jobs(...)` → `reconcile_search_state(session)` → `claim_next_job(...)`. It
  still returns `False` on an empty queue.
- **No migration:** pure Python; no column, table or enum changed (`canceled` deliberately stays out of the search
  enums — `SearchStatus`/`SearchVideoStatus` mirror `DESIGN_DESCRIPTION.md:121`, which names only
  `queued`/`running`/`done`/`failed`).
- `tests/test_searches.py`: new section 7 with `_search_with_two_videos` and four tests —
  `test_execute_job_does_not_resurrect_a_canceled_video`,
  `test_reconcile_repairs_a_video_left_running_by_a_crashed_job`,
  `test_reconcile_settles_a_search_whose_videos_all_finished` (the child rows are committed but the aggregate never
  derived — the window the reaper cannot see because no job is stale, and it asserts the sweep reports the repair),
  `test_reconcile_repairs_a_requeued_job_and_settles_an_idle_search` (also asserts a second sweep returns 0).

**Not done:** `reconcile_search_state` repairs the child row from the job, never the reverse, and does not touch
`ProcessingJob` rows; a job whose `SearchVideo` row was deleted outright is not recreated.

**Verification:** written in a session where the shell executor was a no-op, so the 143 above was arithmetic, not
an observed run: the suite held **135 test functions** at that point; four of them were added in section 7 above.
Two are parametrised (`test_storage.py::test_path_for_rejects_traversal` expands to 6 cases and
`test_worker.py::test_only_failed_jobs_are_retryable` to 4), so `135 − 2 + 6 + 4 = 143` collected was the
prediction. The first real run came after the next increment (three more functions in section 8) and reported
**146 passed**. The suite is now 162 — see the newest entry. Run from `backend/`: `python -m pytest -q` and
`python -m ruff check app tests`.

```bash
cd backend
..\.venv\Scripts\python.exe -m pytest -q          # 146 passed when this was written
..\.venv\Scripts\python.exe -m ruff check app tests
```

## 2026-11-25 — Dataset authorization on the shared legacy routes

**Goal:** a merge-blocker reported in PR review. The dataset routes created in Sprint 3 check membership and
role, but the routes inherited from the single-project API serve the very same rows **by primary key only**:
`GET/DELETE /videos/{id}`, `GET /videos/{id}/stream`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/retry`,
`POST /jobs/{id}/cancel`, `GET /jobs/{id}/candidates` and the whole `/candidates/{id}*` family never resolved a
principal. With `VLM_API_TOKEN` unset (the default in development) any caller could read, stream or delete a
dataset video, and read or cancel a dataset search job, by guessing an id. `VLM_AUTH_REQUIRED=true` did not close
the hole either, because those handlers never depended on an auth dependency at all.

**Code**

- `app/access.py` (new): ownership resolution plus the per-resource guards. `dataset_for_video` reads
  `video.dataset_id`; a job carries no dataset column, so `dataset_for_job` derives it from `job.video_id`, then
  from its `search_videos` row → `searches.dataset_id`, then from a candidate it produced (a `DELETE /videos/{id}`
  nulls `processing_jobs.video_id`, because `Video.jobs` has no `passive_deletes`); `dataset_for_candidate`
  prefers `candidate.search_id` and falls back to the video.
  `_require_membership_then_roles` answers `401` for an anonymous caller, then `404` for a non-member (the
  existence of a dataset must not leak, exactly like `_require_access` in `api/datasets.py`) and `403` for a
  member lacking the role. It runs **inside the handler**, after the row is loaded — binding `require_roles` as a
  route dependency cannot express that order, because dependencies run before the body and a stranger would get
  `403` instead of `404`. `filter_visible_jobs` handles the one list endpoint, which cannot 404 per item.
- `app/deps.py`: new `get_optional_principal`. The shared routes serve legacy project rows that were never
  authenticated, so a required dependency would `401` anonymous callers and break them once `VLM_AUTH_REQUIRED`
  is on. It validates a *presented* token (invalid/expired still `401`) and otherwise returns an anonymous
  principal, letting the per-row guard decide. With authentication switched off it returns the synthetic
  administrator, so development stays unauthenticated end to end.
- `app/api/videos.py`, `app/api/jobs.py`, `app/api/candidates.py`: every shared handler now takes the principal and
  calls the matching guard. `delete_video` authorizes **before** touching anything, so a refused delete leaves the
  row, the stored file and the engine artefacts in place. Writes that change a dataset need `dataset_admin`
  (`DATASET_WRITE_ROLES`); annotating needs only membership, because that is the annotator's job.
  `create_processing_job` now answers `409 PROJECT_MISMATCH` for a dataset video before looking the action up —
  actions belong to projects, and dataset work is launched through `POST /datasets/{id}/searches`.
- `app/api/candidates.py` `list_project_candidates` deliberately takes **no** principal: its query is pinned to
  `Video.project_id == project_id`, and a dataset video has `project_id IS NULL`, so dataset rows cannot appear.
- **No migration:** pure Python; no column, table or enum changed.
- `tests/test_dataset_authz.py` (new, 9 tests): the four-caller matrix (administrator, `dataset_admin` member,
  annotator member, signed-in **non-member who holds the global `dataset_admin` role** — the case the role checks
  alone would get wrong) plus anonymous, across reads and mutations; refusals are asserted to have no side effect
  (the row and the stored bytes survive a refused video delete, a refused cancel leaves the job status untouched,
  a refused annotation creates no row). One test drives the entire legacy project flow unauthenticated to pin that
  nothing changed there.

**Decision to note:** ownership is not always derivable. A search job whose video was deleted has `video_id IS
NULL` **and** `project_id IS NULL`, and the `search_videos` row is gone too, so no join can attribute it. It is
made visible to administrators only and `404` to everyone else — fail closed rather than fall back to "no check".

**Not done:** `annotation.reviewer` still comes from the request payload (`"anonymous"` when empty) instead of the
session identity; that is a separate, deliberate gap so the review UI keeps working for unauthenticated
development.

**Verification:** written in a session where the shell executor was a no-op, so the 134 above was arithmetic (the
prior 125 plus 9 in `test_dataset_authz.py`), not an observed run. Verified later: the suite reported **146 passed**
after the following increment, which includes these 9. The current count is 162 — see the newest entry. Run from
`backend/`: `python -m pytest -q` and `python -m ruff check app tests`.


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

**Verification:** `alembic upgrade head`, `pytest` and `ruff` were not runnable in the session that wrote this
entry (the shell executor was a no-op there). The suite was later confirmed green on Windows at **121 passed** once
the 2026-11-25 lifecycle tests were added; this increment accounted for 114. The current count is 162 — see the
newest entry.
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
