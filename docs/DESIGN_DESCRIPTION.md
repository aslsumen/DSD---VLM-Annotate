# Design Description — working repository copy

**Project:** VLM Annotate · **Customer:** Visage Technologies
**Version:** 1.2 (repository working copy) · **Date:** 2026-11-15 · **Status:** v1.1 PDFs delivered to the team (submission evidence unverified); this copy adds the 9 Nov customer answers
**Aligned with:** team's Design Description v1.1 (`docs/inputs/2026-11-12/VLM_Annotate_Design_Description_v1.1.pdf`)
and the latest customer reply (CE-2).

> **Read this with the requirements.** The target design below is the team's v1.1 design updated with CE-2
> (Dataset Administrators may invite; roles global; email-only accounts). The **implementation status** section
> is separate and honest: the current repository implements a narrower slice.

> **As-built detail for the implemented prototype:** [docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md](as-built/IMPLEMENTED_BASELINE_2026-11-05.md).

## 1. Goals and constraints

1. One loop: **sign-in → dataset → prompt → detection → review → JSON export**.
2. Detection is offline and can take hours: never inside a web request.
3. The model is replaceable (API or self-hosted) behind one interface.
4. Videos may contain faces: storage on approved infrastructure, external AI only with written approval.
5. Roles are global; access is scoped per dataset; accounts exist only by invitation.
6. A distributed team must build it in seven sprints with the course deadlines.

## 2. System context

Six external entities, two of them still unresolved:

| Entity | Role | Status |
|---|---|---|
| Vision-language model | Detect events from a prompt: commercial API (Gemini) or open-source (VideoJev-4B/Qwen) | VideoJev-4B is integrated as the first real detector ([ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md)); Gemini verify exists but is off in the product adapter; Qwen-VL is a stub |
| Compute | Runs or calls the model: GPU server, 12 GB laptop, or API | **Open** — 12 GB laptops offered, remote access TBD |
| Server + database hosting | Hosts the app, videos, annotations | **Open** — customer vs university |
| Email service | Invitations and password resets | **Open** — SMTP vs transactional provider |
| Video datasets | Test and real footage | Public datasets selected (see `MODEL_EVALUATION.md`) |
| Downstream training | Consumes exported JSON | Customer side, not built |

## 3. Target architecture (v1.2)

```
 React SPA ──HTTPS/JWT──► FastAPI backend ──SQL──► PostgreSQL
     │                        │
     │ signed links            ├── enqueue ──► Redis (Celery broker)
     ▼                        │
 object storage ◄─────────────┴── Celery workers ──in-process──► Detection engine (GPU)
 (videos, clips, export)                                            │
                                                              VideoJev-4B (library)
```

| Component | Responsibility | Proposed technology |
|---|---|---|
| Web client | Sign-in, datasets, upload, search, review, export, user management | React + TypeScript |
| Backend API | Auth/roles, dataset access checks, upload registration, search/export jobs, signed media links | FastAPI (Python) |
| Task queue | Long-running detection and export jobs | Celery + Redis |
| Workers | One detection job per video; call the engine; store candidates; cut preview clips | Celery workers |
| Detection engine | Windowed zero-shot grounding, fusion, flags, clips, KPIs | Python library (`video_grounding/`) loaded by the GPU worker; also a debug/eval CLI |
| Database | Users, sessions, invitations, datasets, videos, searches, candidates, exports | PostgreSQL |
| Object storage | Source videos, preview clips, export archives | MinIO or S3 |
| Deployment | Reproducible single-command setup | Docker Compose |

**Why a separate engine package:** it pins the model, GPU and memory profile; the API process does not import it
(only the GPU worker does); the same package runs on a laptop with a low-VRAM profile or on a GPU server, and CI
can replay recorded outputs without a GPU. It has no HTTP server (removed; the backend owns queueing, review
and export), so a separate engine service is not built.

## 4. Current implementation vs target (honest status)

| Target concern | Current repository (2026-11-12) |
|---|---|
| React SPA | **Exists** (projects, workspace, review) — screens for auth/datasets/searches missing |
| FastAPI API | **Exists**, but domain is Project/Action, not Dataset/Search |
| Celery + Redis | **Not used** — DB-backed queue + single worker process |
| PostgreSQL | **SQLite**; models are PostgreSQL-portable, no deployment tested |
| Object storage | **Local filesystem** behind a `StorageBackend` protocol |
| Detection engine | `mock` adapter is the default (deterministic, labelled); `videojev` adapter runs the VideoJev-4B engine in the worker (opt-in, GPU). Backend tests (fake engine) and engine tests pass; real-model smoke on the 8 GB laptop is pending (2026-11-16). Gemini verify is off in the adapter |
| Auth | **Optional single bearer token**; no users, roles, invitations, sessions |
| Export | **ZIP + manifest + CSV**; no OpenLABEL JSON |
| Tests | 80 backend + 21 UI + real-ffmpeg smoke (26/26) |

**Reuse:** media upload/probe/range streaming, clip extraction, job queue semantics, candidate model with
proposal/preview separation, review API/UX, provenance, error envelope, test harness.
**Replace/expand:** domain model (Dataset/Search), auth/roles/permissions, export format, detector backend,
deployment packaging.

## 5. Data model (target)

| Entity | Key fields | Notes |
|---|---|---|
| User | id, email, password_hash, role, status, failed_sign_ins, locked_until | Global role: administrator / annotator / dataset_admin |
| Invitation | id, email, role, token_hash, invited_by, expires_at, used_at | Single-use, 48 h (NFR-11); inviter may be Admin or Dataset Admin (CE-2) |
| Session | id, user_id, refresh_token_hash, last_activity_at, expires_at, revoked_at | Sign-out revokes; inactivity expiry 2 h proposed |
| Dataset | id, name, use_case, created_by, created_at | Ownership scopes Dataset Admin rights |
| DatasetAssignment | user_id, dataset_id, assigned_by, assigned_at | Composite PK; grants access |
| Video | id, dataset_id, file_name, storage_key, duration_s, resolution, status, summary, tags | `summary`/`tags` empty until EXP-3 (non-MVP) |
| Search | id, dataset_id, prompt, model_config_id, status, created_by, timestamps, error | One prompt per search, all videos of the dataset |
| ModelConfig | id, provider_type, model_name, frame_rate, resolution, parameters | `api` or `self_hosted`; makes KPIs reproducible |
| Candidate | id, search_id, video_id, original_start_s, original_end_s, start_s, end_s, confidence, preview_key, review_status, reviewed_at, reviewer_id, needs_review, review_reasons | Raw and final times kept separately; flags from ENG-6 |
| Export | id, dataset_id, search_id (optional), status, storage_key, include_rejected, created_by, timestamps | Async (EXP-1) |

Relations: Dataset 1–N Video/Search/Assignment; Search 1–N Candidate; Candidate N–1 Video; User 1–N Sessions,
Assignments, Searches. Deleting a dataset cascades its videos/searches/candidates/assignments; users are
deactivated, not deleted.

## 6. Access control and account lifecycle

1. **Invitation:** Admin or Dataset Admin submits email + role (+ datasets for assignment). A single-use token
   is emailed; the person sets a password; the account becomes active. No username (CE-2).
2. **Sign-in:** email + password. Passwords hashed (Argon2/bcrypt). Session token in an http-only cookie or
   bearer JWT — open decision; sign-out revokes server-side.
3. **Authorization:** every request resolves the user's global role and dataset scope; Dataset Administrators
   act only within datasets they created or were assigned; Annotators only within assigned datasets.
4. **Lockout/session:** 5 failed attempts in 15 min → 15 min block, neutral message (NFR-14); 2 h inactivity
   expires the session (NFR-13); unsaved review edits survive re-authentication.
5. **Deactivation:** Admin sets `status=deactivated`; sessions revoked; history kept.

## 7. Search and detection flow

1. User selects a dataset, writes one prompt, launches a search.
2. API validates access, creates `Search(status=queued)`, enqueues one Celery job **per video**, returns the
   search id immediately (202).
3. Each worker passes the video (or a signed URL/path) + prompt to the detection engine in-process, receives
   events, stores candidates with raw times, flags and preview clips.
4. Search state aggregates video jobs: `queued → running → done`, or `failed` with per-video partial results.
5. Review reads candidates across all videos of the search in one list; decisions update `review_status`,
   final times, reviewer.
6. Export re-cuts adjusted clips as needed and writes the JSON artifact asynchronously.

## 8. Detection engine (v1.1 §6.1, adapted)

- **Model:** VideoJev-4B (Apache-2.0, Qwen3.5-4B base, revision pinned in
  `video_grounding/src/video_grounding/adapters/videojev.py`) is the self-hosted detector. **Gemini API** is an
  optional verify stage (`gemini-decision-1`, key supplied by the customer), off in the product adapter (why: §8.1). Qwen-VL is a
  registered stub. Backends sit behind `GroundingBackend`.
- **Pipeline:** probe → 30 s windows / 20 s stride → cut ≤720p window clips → sample 1 FPS (≤32 frames) →
  score curve → map to source time → fuse on a 0.5 s grid with edge weighting → hysteresis (0.25/0.15) →
  `fusion.min_event_score` filter (0.5) → refine candidates at 2 FPS (≤64 frames) with expanding windows →
  optional Gemini verify → completeness flags → clip export → `events.json`. Defaults:
  `video_grounding/configs/default.yaml`.
- **Timestamp integrity:** PTS minus stream start; frame-pair sampling; alignment marked exact/estimated/unknown;
  engine never guesses when probability and timestamp arrays disagree (`AlignmentError`).
- **Resume/idempotency:** window-level SQLite journal; job-local results; stable `event_id` hash; re-run skips
  succeeded windows.
- **Hardware profiles:** `reference_gpu`, `dev_low_vram` (8 GB laptop, `configs/rtx3070.yaml`, CPU offload; OOM ladder lowers the frame count),
  `replay` (CI without GPU).

### 8.1 Why the engine is built this way

Charades-STA numbers below are reference only: VideoJev was trained on it (`video_grounding/docs/EVALUATION.md`).

| Decision point | Choice | Why (evidence) |
|---|---|---|
| Detector | A temporal-grounding model (VideoJev-4B), not a captioning VLM | It returns a per-frame score curve, so boundaries come from scores rather than from text the model writes; it runs on the 8 GB dev GPU with CPU offload (ADR-0007). |
| Long videos | Overlapping 30 s windows, 20 s stride | One model call sees at most 32 frames. Overlap means an event cut by one window edge is seen whole by its neighbour; fusion down-weights window edges. |
| Two passes | Cheap coarse scan (1 fps / 32), then refine only around candidates (2 fps / 64) | The coarse pass decides *where*, refine decides *the boundaries*, so dense sampling is paid only near events. Doubling coarse sampling (0.5 → 1 fps) raised recall 0.598 → 0.672 and halved queries with no event (21.3% → 10.9%). Refining at 4 fps / 120 frames did not help (R1@0.5 0.440 vs 0.486) and cost 1.6× the refine time, so 2 fps stays. |
| Turning a curve into events | 0.5 s grid, hysteresis 0.25 / 0.15, then `min_event_score` | Hysteresis keeps a noisy curve from splitting one action into fragments. Narrower fusion (higher segment threshold, trimming to 50% of peak) made every length bin worse: wide events come from the model scoring a long stretch high, not from fusion. `min_event_score` 0.9 → 0.5 gave recall +8.1 points and cut queries with no event 12.3% → 1.1% for −3.1 points precision; checked on the held-out long videos (3.5 candidates per absent cooking prompt, 8.4 per absent driving prompt): kept, but on driving it does not separate present from absent prompts. |
| Verify stage | Optional yes/no check *after* refine that can only remove events | It asks about the final clip, so it judges what the reviewer would see, costs one call per event, and can never move a boundary. Added because of false events on other test sets: on one YouCook2 composite the model proposed 134 false events next to 13 true ones, and absent prompts (actions not in the video) still produced events. Qwen3-VL-4B (offline) fixed the absent prompts but did not help on driving footage. `gemini-decision-1` removed 197/220 false cooking events with 0/26 true ones lost, and all 88 absent-prompt events. |
| Verify default | Off; always off in the product adapter | On driving footage it cost recall (BDD-X: 8/36 true events lost; Nexar crashes: 1/8 kept). On Charades, where every query happens, it removed 35% of false events for −14 points recall. The human reviewer already removes false events, and keeping it off means no footage leaves the machine. |
| Failure handling | SQLite journal per window, stable `event_id`, OOM ladder | Hours-long jobs resume after a crash (a real run killed with `kill -9` at unit 189 resumed from there); an OOM lowers the frame count instead of failing the job. |

## 9. Export format — proposal for the customer (Q4)

The customer asked the team to propose the structure, referencing an OpenLABEL-based example that we do **not**
have in the repository. The team should send this one-page proposal by **2026-11-17** and confirm it before
implementing. Sketch:

```json
{
  "schema_version": "1.0",
  "exported_at": "2026-11-20T10:00:00Z",
  "dataset": {"id": "…", "name": "Warehouse operations", "use_case": "warehouse"},
  "search": {"id": "…", "prompt": "Person opens a door", "created_at": "…"},
  "model": {"name": "videojev-4b", "revision": "…", "provider": "self_hosted", "frame_rate": 1.0},
  "videos": [
    {
      "id": "…", "file_name": "cam01_0915.mp4", "duration_s": 300.0,
      "resolution": "1920x1080", "status": "ready",
      "summary": null, "tags": []
    }
  ],
  "actions": [
    {
      "id": "action_0",
      "name": "Person opens a door",
      "type": "application-defined:door_opening",
      "video_id": "…",
      "intervals": [
        {"start_s": 42.0, "end_s": 47.5, "start_frame": 1050, "end_frame": 1187},
        {"start_s": 120.0, "end_s": 122.0, "start_frame": 3000, "end_frame": 3050}
      ],
      "review": {
        "status": "accepted",
        "reviewer_email": "annotator@example.com",
        "reviewed_at": "2026-11-19T15:12:00Z",
        "original_intervals": [{"start_s": 41.2, "end_s": 47.9}]
      },
      "clip": {"file": "clips/cam01_0915_action_0.mp4", "preview_start_s": 41.7, "preview_end_s": 48.0},
      "flags": {"complete": "likely", "needs_review": false, "review_reasons": []}
    }
  ]
}
```

Open points for the customer: reject-as-negative block, whether clips must be included, whether reviewer
identity is required (Q2), and whether `type` strings must match a controlled vocabulary.

## 10. API (target)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/login`, `/logout`, `/refresh`, `/password-reset` | Session lifecycle |
| POST | `/api/users/invitations`, `/invitations/accept` | Invitation flow |
| GET/PATCH | `/api/users`, `/api/users/{id}` | Roles, deactivation |
| GET | `/api/me` | Current user + role |
| GET/POST | `/api/datasets`; `/api/datasets/{id}` | Dataset list/create/detail |
| POST/GET | `/api/datasets/{id}/videos` | Register/upload + list videos |
| POST | `/api/datasets/{id}/searches` | Create a search (prompt) |
| GET | `/api/searches/{id}`, `/searches/{id}/candidates` | Status and results |
| PATCH | `/api/candidates/{id}` | Final times, review status, reviewer |
| POST/GET | `/api/exports`, `/api/exports/{id}` | Async JSON export + download |
| GET | `/api/health` | Liveness/readiness |

Conventions: JSON error envelope; pagination envelope (`items`, `total_items`, `current_page`); 202 + polling for
long operations; signed short-lived media URLs; role checks on every route.

The **current implemented API** (`/api/v1/projects`, `/actions`, `/videos`, `/jobs`, `/candidates`, `/exports`)
is documented in `docs/API_CONTRACTS.md`; it will be migrated, not maintained in parallel.

## 11. Non-functional design

- **Privacy:** self-hosted detection by default; API use only with written approval; signed media URLs; no
  secrets in Git; deletion cascades; retention configurable.
- **Security:** hashed passwords, single-use 48 h invitations, server-side session revocation, neutral login
  errors, lockout, role/dataset checks, upload validation, path traversal protection.
- **Performance:** detection offline; API is I/O-light; preview clips pre-cut; pagination; 24 h search target.
- **Reliability:** per-window journal and resume; per-video partial failures; retry/backoff; stable IDs.
- **Deployability:** Docker Compose; documented configuration; health endpoints.

## 12. Open design decisions

| Decision | Options | Depends on |
|---|---|---|
| Detection model | VideoJev-4B chosen as first real detector (ADR-0007); Gemini verify optional/off; Qwen-VL stub | Held-out long videos 2026-11-22: recall 0.86 cooking / 0.47 driving vs 0.85, targets not met or not confirmed (EVALUATION.md); Charades-STA is reference only; product-footage validation |
| Compute | Gemini API / 12 GB laptop / 24 GB GPU / AWS | Customer + supervisors |
| Hosting | Customer / university / cloud | Supervisors |
| JSON schema | Team proposal §9 / customer example | Customer (by 2026-11-17) |
| Auth scheme | http-only cookie session / JWT bearer | Team (Sprint 3 planning) |
| Stack migration | keep DB-queue + SQLite + local storage for MVP, or move to Celery/Redis/Postgres/MinIO | Team capacity |
| Review flags in DB | store `needs_review`/reasons or engine-only | Team |
| Email service | SMTP host vs provider | Hosting |
| Session limits | 2 h / 5 attempts / 15 min | Customer |
| KPI targets | proposed values | Customer |

## 13. Trade-offs recorded

| Decision | Alternative | Why |
|---|---|---|
| Engine as a library in the GPU worker (ADR-0007) | separate engine service over HTTP | One fewer service and no HTTP hop; the engine package still isolates model/GPU settings and replays in CI; API process never imports it |
| Async search + polling | synchronous request | hours-long detection (NFR-3) |
| Global roles | per-dataset roles | Customer preference; simpler authorization (CE-2) |
| Keep raw + final timestamps | overwrite on review | Required for boundary-precision KPI (NFR-5) |
| English-only UI copy for now | i18n | Team time; customer works in English |

## 14. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 (repo) | 2026-11-05 | First repository design: project/action vertical slice |
| **1.2 (repo)** | **2026-11-12** | Aligned to team v1.1 + CE-2: global roles, Dataset Admin invitations, email-only accounts, dataset/search model, JSON export proposal, engine service, honest implementation status |
| 1.3 (repo) | 2026-11-16 | Engine is a library in the GPU worker (ADR-0007), `videojev` adapter integrated (real-model smoke pending), pipeline and defaults updated, Gemini verify off in the adapter |
| 1.4 (repo) | 2026-11-22 | §8.1: each engine design decision with the evidence behind it, including why verify runs after refine |
