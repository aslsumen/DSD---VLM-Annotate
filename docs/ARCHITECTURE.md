# Architecture — v1.2 target and current state

**Date:** 2026-11-12 · **Status:** target for the v1.1 requirements; current repository implements a narrower
slice · **See also:** [DESIGN_DESCRIPTION.md](DESIGN_DESCRIPTION.md), [API_CONTRACTS.md](API_CONTRACTS.md),
[DATABASE_SCHEMA.md](DATABASE_SCHEMA.md).

> **As-built detail for the implemented prototype:** [docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md](as-built/IMPLEMENTED_BASELINE_2026-11-05.md).

## 1. Drivers

| Driver | Consequence |
|---|---|
| Detection can take hours (NFR-3) | Search and export are asynchronous jobs; HTTP only enqueues |
| Videos may contain faces (NFR-8) | Self-hosted detector by default; cloud API only with written approval; signed media URLs |
| Roles are global, access is per dataset (CE-2) | Authorization on every route; dataset scoping for Dataset Administrators |
| The model may change (NFR-6) | One `GroundingBackend` interface; model pinned per `ModelConfig` |
| 12 GB VRAM available, 24 GB maybe | Windowed processing, low-VRAM profile, quantisation |
| Distributed team, 7 sprints | Modular services, Docker Compose, stable contracts |

## 2. Target architecture

```mermaid
flowchart LR
    UI["React + TypeScript SPA<br/>auth · datasets · review · export"]
    API["FastAPI backend<br/>auth/RBAC · uploads · searches · exports"]
    Q[("Redis<br/>Celery broker")]
    W["Celery workers<br/>1 job per video"]
    E["Detection engine service<br/>VideoJev-4B / Gemini adapter"]
    DB[("PostgreSQL<br/>users · datasets · searches · candidates")]
    S[("Object storage<br/>videos · clips · exports")]
    M["Email service<br/>invitations · resets"]

    UI -- "HTTPS/JWT or cookie" --> API
    API --> DB
    API -- "enqueue" --> Q
    Q --> W
    W -- "HTTP job" --> E
    W --> DB
    W --> S
    API -- "signed URLs" --> S
    API --> M
```

| Component | Responsibility |
|---|---|
| SPA | Sign-in, invitation acceptance, dataset pages, upload with progress, search launch, cross-video review, export, user management |
| API | Authentication, RBAC + dataset scoping, upload registration, search/export job creation, polling, signed media links |
| Queue/workers | Fan out one detection job per video; aggregate search state; persist candidates; cut preview clips |
| Detection engine | Windowed grounding, fusion, completeness flags, clip export, resume, KPI computation |
| PostgreSQL | Metadata, users, assignments, searches, candidates, review state |
| Object storage | Source videos, preview clips, JSON/clip export artifacts |
| Email | Invitations (48 h single-use) and password resets |

**Deployment:** Docker Compose on a single host (API, workers, Redis, PostgreSQL, MinIO, engine with GPU
profile, web build). The engine can also run on a separate GPU machine.

## 3. Current repository (verified 2026-11-12)

```mermaid
flowchart LR
    UI["React SPA<br/>projects · workspace · review"]
    API["FastAPI<br/>projects/actions/videos/jobs"]
    W["JobWorker process<br/>poll DB queue"]
    A["Adapters<br/>mock · videojev (GPU, worker only)"]
    DB[("SQLite<br/>7 tables")]
    FS[("Local storage<br/>videos · clips · exports")]
    UI --> API
    API --> DB
    API --> FS
    W --> DB
    W --> A
    W --> FS
```

- One API process + one worker process; queue in the database (`UPDATE … WHERE status='queued'`), no Redis.
- SQLite with WAL; Alembic migration verified. PostgreSQL-compatible models but untested.
- Local storage behind a `StorageBackend` protocol; generated keys, traversal guard.
- Optional single bearer token enforced in middleware; **no users/roles/datasets**.
- Adapters: `mock` (CI default), `videojev` (real detector, the `video_grounding/` engine with VideoJev-4B, run
  in the worker process only; [ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md)), and a
  registered `qwen2.5-vl` stub. The `videojev` adapter is *exhaustive* (all events kept, zero events is
  success), resumes from a per-job work dir `data/storage/engine/job-<id>/` on retry, and loads the model once
  per worker. `POST /projects/{id}/actions/{id}/jobs` queues one job per video.
- Export is a ZIP with `manifest.json` + `labels.csv` + clips (not OpenLABEL JSON).

**Tests:** 69 backend (pytest), 21 UI (vitest), real-ffmpeg smoke 26/26; real-model `scripts/smoke_videojev.py` (GPU host).

## 4. Gap and migration plan

| Target element | Current | Migration |
|---|---|---|
| PostgreSQL | SQLite | Keep models portable; add Compose service; run migrations; test |
| Redis + Celery | DB queue | Introduce Celery only if throughput/parallelism demands it; otherwise keep DB queue as a documented simplification (decide Sprint 3) |
| Object storage | Local FS | Implement `StorageBackend` for S3/MinIO; signed URL issuance belongs to the API |
| Users/roles/invitations | Bearer token | New auth module, tables and screens; RBAC middleware; dataset scoping |
| Dataset/Search domain | Project/Action | Rename + new entities; data migration for existing rows; adapt UI |
| Detection engine | `videojev` adapter in the worker (in-process) | Separate engine service + Gemini backend only if GPU hosting must be split from the worker |
| JSON export | ZIP/CSV | New async export job writing the schema in Design §9 |
| Signed media URLs | Token or open | Time-limited signed URLs/cookies so `<video>` works (also fixes R-18) |

## 5. Key flows (target)

### 5.1 Search fan-out

1. `POST /api/datasets/{id}/searches` validates access and creates `Search(status=queued)`.
2. API enqueues one job per video (Celery) and returns `202 {search_id}`.
3. A worker posts each video to the engine (`POST /v1/jobs`), polls, receives events, writes candidates and
   preview clips.
4. Search state aggregates child jobs; partial failures are reported per video (NFR-9).
5. The client polls `GET /api/searches/{id}`.

### 5.2 Review

`GET /api/searches/{id}/candidates` returns one paginated list across all videos with filters (video, review
status, confidence). `PATCH /api/candidates/{id}` stores final timestamps, `accepted/rejected`, reviewer and
time; raw proposal values are never overwritten.

### 5.3 Export

`POST /api/exports` → `202`; worker collects accepted (and optionally rejected) annotations, re-cuts adjusted
clips, writes JSON (schema in Design §9) to object storage; `GET /api/exports/{id}` exposes status + signed
download URL.

## 6. Failure handling

| Failure | Behaviour |
|---|---|
| Engine unavailable / model OOM | Job retried with fewer frames (ENG-11); after retries, per-video failure reported; search completes partially |
| Window failure | Window marked coverage gap; search flags it (ENG-4) |
| Worker crash | Job journal resumes finished windows (ENG-9); search can be retried |
| API rate limit (Gemini 429) | Exponential backoff with a daily budget guard |
| Upload invalid | 4xx with error envelope; file not retained |
| Session expiry during review | Client keeps unsaved edits and replays after re-authentication (NFR-13) |

## 7. Security architecture

- TLS everywhere; http-only cookies or short-lived JWT with refresh rotation (decision pending).
- Passwords hashed (Argon2id/bcrypt); invitation tokens stored hashed, single-use, 48 h.
- RBAC middleware + per-dataset authorization; deny by default.
- Signed, short-lived media URLs; no public object buckets.
- Upload validation: extension + MIME + container signature + size + duration + probe.
- Secrets only in environment/secret store; Gemini key never in Git.
- Audit-relevant fields: `created_by`, `reviewer_id`, timestamps; deletion cascades; users deactivated not deleted.

## 8. Scaling path

1. More workers (Celery) and a second GPU engine instance.
2. Object storage + CDN for signed media.
3. Read replicas for review-heavy datasets.
4. Batch scheduling per dataset to respect API quotas.

## 9. Open architectural decisions

Auth scheme (cookie vs JWT) · stack migration scope (Celery/Redis/Postgres/MinIO vs keep DB queue for MVP) ·
engine deployment target (12 GB laptop vs 24 GB GPU vs API) · signed-URL issuer (API vs storage) · retention
policy.
