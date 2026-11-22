# Product Backlog

**Type:** living artifact · **Owner:** Product Owner (role placeholder) · **Last updated:** 2026-11-16
**Access:** versioned in Git. Supervisor read access is **NOT yet configured** — see `R-12`.

Priority: **M**ust / **S**hould / **C**ould. Estimates are **provisional story points** for relative sizing,
not person-hours. Team velocity is unknown until Sprint 2 closes, so all sizing must be recalibrated then.

## 1. Epics

| Epic | Goal | Status |
|---|---|---|
| E1 Platform foundation | Projects, actions, configuration, migrations | Done |
| E2 Media pipeline | Upload, validate, probe, stream, delete | Done |
| E3 Async processing | Queue, worker, retries, progress, cancellation | Done |
| E4 Candidate review | Timestamp contract, clips, TP/FP labelling, corrections | Done (API) / in progress (UI) |
| E5 Dataset export | Verified labels, media, provenance | Done |
| E6 Real VLM inference | Qwen2.5-VL windowed localization on real footage | Superseded 2026-11-16 by E13 / [ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md) (VideoJev-4B is the first real model; Qwen2.5-VL stays a stub) |
| E7 Hardening & operations | Security, retention, observability, packaging | Partial |
| E8 Course delivery | Backlogs, burndown, decks, reports, acceptance | In progress |
| E9 Optional | Multi-model, comparison UI, active learning, tracking | Deferred |
| E10 Accounts and access | Users, **global roles**, invitations, sessions, sign-out, lockout | Not started — MVP Must |
| E11 Dataset and search domain | Dataset entity, assignments, search = one prompt over all videos | Not started — MVP Must |
| E12 JSON export (OpenLABEL) | Multi-interval JSON, reviewer provenance, optional negatives | Not started — MVP Must |
| E13 Detection engine | Windowed grounding, fusion, flags, clips, VideoJev-4B backend, optional Gemini verify | In progress — MVP Must (engine + `videojev` adapter integrated; real-model smoke and product-footage validation pending) |

## 2. Backlog items

| ID | Epic | Item | Prio | Est. | Status | Sprint | Notes |
|---|---|---|---|---|---|---|---|
| PB-01 | E1 | Project CRUD with description | M | 2 | Done | 2 | API + tests |
| PB-02 | E1 | Action definitions with natural-language description | M | 2 | Done | 2 | Unique name per project |
| PB-03 | E1 | Pydantic schemas + error envelope | M | 3 | Done | 2 | `VALIDATION_ERROR` etc. |
| PB-04 | E1 | Alembic migrations | M | 3 | Done | 2 | Verified on fresh SQLite |
| PB-05 | E2 | Video upload with size/extension/signature validation | M | 5 | Done | 2 | 2 GiB default cap |
| PB-06 | E2 | ffmpeg probe (duration/resolution/fps) | M | 3 | Done | 2 | Bundled via imageio-ffmpeg |
| PB-07 | E2 | HTTP Range streaming of source video | M | 3 | Done | 2 | Needed for seeking |
| PB-08 | E2 | Cascade delete of media files | S | 2 | Done | 2 | Storage cleanup |
| PB-09 | E3 | DB-backed job queue with atomic claim | M | 5 | Done | 2 | Postgres SKIP LOCKED path documented |
| PB-10 | E3 | Separate worker process + CLI (`--once/--loop/--drain`) | M | 3 | Done | 2 | |
| PB-11 | E3 | Retry with backoff, max attempts, manual retry | M | 5 | Done | 2 | Idempotent re-run |
| PB-12 | E3 | Progress + structured errors | M | 3 | Done | 2 | Code + message on the job |
| PB-13 | E3 | Cancel queued jobs | S | 2 | Done | 2 | Running cancel deferred |
| PB-14 | E3 | Idempotency-Key on job creation | S | 2 | Done | 2 | |
| PB-15 | E4 | Candidate intervals with proposal/preview separation | M | 5 | Done | 2 | Clamp + note |
| PB-16 | E4 | Real clip extraction + per-candidate error state | M | 5 | Done | 2 | Verified with real ffmpeg |
| PB-17 | E4 | Annotation upsert with TP/FP and corrections | M | 5 | Done | 2 | Validation server-side |
| PB-18 | E4 | Unreviewed distinct from negative | M | 3 | Done | 2 | No annotation row |
| PB-19 | E4 | Review queue filters + stats | S | 3 | Done | 2 | |
| PB-20 | E4 | Responsive review UI with keyboard flow | M | 8 | Done | 2 | Frontend build + 21 tests |
| PB-21 | E5 | Async ZIP export | M | 5 | Done | 2 | |
| PB-22 | E5 | manifest.json / labels.csv / README / clips | M | 5 | Done | 2 | Schema 1.0 |
| PB-23 | E5 | Refuse export with nothing reviewed | M | 2 | Done | 2 | Override flag |
| PB-24 | E6 | Qwen2.5-VL adapter: windowed inference | M | 13 | Superseded | 3 | ADR-0007: VideoJev-4B is the first real model; adapter stays a stub |
| PB-25 | E6 | Real-footage evaluation set + metrics | M | 8 | In progress | 3 | Recall@IoU etc. Charades-STA reference run done (`video-grounding eval`); held-out long-video benchmark (`heldout_bench.py`) done in PB-70 (2026-11-22); product-footage set not started |
| PB-26 | E6 | Model selection ADR with measured evidence | M | 3 | Done | 3 | ADR-0007 (2026-11-16) supersedes provisional ADR-0004; evidence is a Charades-STA reference run (in-domain, integration/timing only); accuracy evidence from the held-out long videos (PB-70, 2026-11-22): cooking recall 0.86 (CI 0.81–0.90), driving 0.47, CCR 0.78 / 0.82, targets not confirmed, the integration decision stands |
| PB-27 | E7 | Retention policy + purge job for old exports | S | 5 | Not started | 4 | `R-06` |
| PB-28 | E7 | Stale running-job reaper | S | 3 | Done | 4 | `R-07` |
| PB-29 | E7 | Structured logging + request ids | C | 3 | Not started | 4 | |
| PB-30 | E7 | Docker/compose packaging | S | 5 | Not started | 4 | Deployment docs |
| PB-31 | E8 | Living Scrum artifacts + supervisor access | M | 3 | In progress | 2 | Human action needed |
| PB-32 | E8 | Requirements & Design deck | M | 5 | In progress | 2 | Upload Nov 9 |
| PB-33 | E8 | Acceptance Test Plan slides | M | 5 | Not started | 5 | Due Dec 25 |
| PB-34 | E8 | Acceptance Test Report slides | M | 5 | Not started | 6 | Due Jan 4 |
| PB-35 | E8 | Installation + user manuals | M | 3 | In progress | 2 | |
| PB-36 | E8 | Final Report ≤ 20 pages | M | 13 | Not started | 7 | |
| PB-37 | E9 | Multiple VLMs + comparison UI | C | 13 | Deferred | — | Only after MVP |
| PB-38 | E9 | Bulk review / advanced shortcuts | C | 5 | Deferred | — | |
| PB-39 | E9 | Active learning / fine-tuning | C | 21 | Deferred | — | Research risk |
| PB-40 | E9 | Tracking / identity, multi-camera, audio | C | 34 | Deferred | — | Out of scope |
| PB-41 | E7 | Media authentication for token deployments (signed URLs/cookies) | S | 5 | Not started | 4 | `R-18` — blocks protected deployment |
| PB-42 | E7 | Commit the browser E2E as a repeatable Playwright test | S | 5 | Not started | 4 | Evidence currently not reproducible in CI |
| PB-43 | E10 | User accounts + email/password authentication (hashed) | M | 8 | Not started | 3 | USR-1, NFR-11; CE-2: email-only |
| PB-44 | E10 | Global roles and RBAC middleware (admin / dataset_admin / annotator) | M | 8 | Not started | 3 | USR-2, permissions table |
| PB-45 | E10 | Invitations by email: single-use token, 48 h, acceptance page; Admin **and Dataset Admin** | M | 8 | Not started | 3 | USR-4/USR-5, NFR-11, CE-2 |
| PB-46 | E10 | Sessions: sign-out, 2 h inactivity expiry, 5-failure/15-min lockout | M | 5 | Not started | 3 | NFR-12…NFR-14 |
| PB-47 | E10 | Password reset by email | S | 3 | Not started | 4 | USR-6 |
| PB-48 | E10 | User deactivation | S | 2 | Not started | 4 | USR-7 |
| PB-49 | E11 | Dataset entity replacing Project (name, use_case, created_by) | M | 5 | Not started | 3 | DS-1/DS-2 |
| PB-50 | E11 | Dataset assignments (user ↔ dataset) and scoped access checks | M | 5 | Not started | 3 | USR-3/USR-4 |
| PB-51 | E11 | Search entity: one prompt over all videos, per-video fan-out, status aggregation | M | 8 | Not started | 3 | PR-1, DET-3 |
| PB-52 | E11 | Search history and prompt reuse | C | 3 | Not started | 5 | PR-2 |
| PB-53 | E12 | OpenLABEL-based JSON export with multiple intervals per action | M | 8 | Not started | 4 | EXP-1; schema proposal due 2026-11-17 |
| PB-54 | E12 | Optional rejected-as-negatives export | C | 2 | Not started | 5 | EXP-2 |
| PB-55 | E12 | Reviewer attribution in export (pending customer answer) | M | 2 | Not started | 4 | EXP-1, REV-3, Q2 |
| PB-56 | E13 | Detection engine service + `GroundingBackend` interface | M | 13 | Done | 3 | Built as a library in the worker, not a service (ADR-0007); ENG-1…ENG-13 not individually re-assessed |
| PB-57 | E13 | Gemini API backend (quota guard, retry, prompt template, validation) | M | 8 | Deferred | 3 | Exists only as the engine's optional verify stage (off in the adapter; little precision gain on Charades-STA, costs recall); not the first detector. Privacy approval R-20 needed only if verify is on |
| PB-58 | E13 | VideoJev-4B self-hosted backend, low-VRAM profile | M | 13 | In progress | 3–4 | `videojev` adapter integrated 2026-11-16, 8 GB profile `rtx3070.yaml`; real-model smoke on the laptop pending |
| PB-59 | E13 | Window planning, fusion, hysteresis, completeness flags | M | 8 | Done | 4 | In the engine (`video_grounding/`); SPEC targets checked on held-out long videos 2026-11-22 (PB-70): not met (driving) or not confirmed (cooking), see PB-71; Charades-STA is reference only |
| PB-60 | E7 | Signed media URLs (fixes R-18) | S | 5 | Not started | 4 | NFR-8 |
| PB-61 | E11 | Pagination envelopes for datasets/videos/candidates/users | S | 3 | Not started | 4 | NFR-7 |
| PB-62 | E4 | Thumbnails in the candidate list | C | 2 | Not started | 5 | REV-1 |
| PB-63 | E7 | Docker Compose packaging (API, workers, Postgres, Redis, MinIO, engine) | S | 8 | Not started | 4 | NFR-10 |
| PB-64 | E11 | Enforce MP4-only and 720p/1080p validation; 5 min Must / 30 min Should | M | 3 | Not started | 3 | DS-4/DS-5, NFR-4 |
| PB-65 | E13 | KPI measurement harness (recall, R@IoU, complete-clip, boundary adjustment) | M | 5 | In progress | 4 | NFR-5. Engine `eval` CLI covers recall/R@IoU/CCR (Charades-STA is reference only, in-domain for VideoJev; the main benchmark is the held-out long-video set, PB-70); reviewer boundary-adjustment KPI not built |
| PB-66 | E13 | Test-dataset ingestion (Charades-STA, TimeLens-Bench) + licence review | M | 5 | Done | 3 | Charades-STA only (`video_grounding/scripts/charades_sta.py`); TimeLens-Bench not used; non-commercial licence caveat in `MODEL_EVALUATION.md` §7 |
| PB-67 | E9 | Automatic video summaries + tags (non-MVP) | C | 8 | Deferred | — | EXP-3; explicitly outside MVP |
| PB-68 | E9 | Scene search over summaries/tags | C | 8 | Deferred | — | SRCH-1 |
| PB-69 | E7 | Mobile review validation (Android Chrome, iOS Safari) | C | 3 | Not started | 6 | NFR-2 (Could) |
| PB-70 | E13 | Run held-out benchmarks (`heldout_bench.py`: YouCook2 33 long videos, ROAD 20; earlier small composites via `composite_bench.py`), re-check `min_event_score`, report KPIs | M | 5 | Done | 3 | NFR-5. Done on the RTX 3070 laptop; results in `video_grounding/docs/EVALUATION.md`. Long videos (2026-11-20 to 22, main KPI source): recall 0.86 [0.81, 0.90] cooking, 0.47 [0.39, 0.56] driving; CCR 0.78 / 0.82; target 0.85 each, so cooking recall is a point-estimate pass only and the rest miss. The earlier small composites (2026-11-17: recall 0.573 pooled) were too small (CI about ±0.13) and are superseded. Replaces Charades-STA as the accuracy check (R-27). `min_event_score` 0.5 checked on the long videos (3.5 / 8.4 candidates per absent cooking / driving prompt); re-tuning stays in PB-72 |
| PB-71 | E13 | Raise driving recall (long videos: lateral moves 0/24, overtake 3/12, stop 35/100, turns found) and cut false candidates on absent prompts (driving 8.4 vs 9.2 per present prompt, cooking 3.5 vs 5.9) | M | 8 | Not started | 4 | NFR-5, R-26, R-27. Follow-up to PB-70; optional Gemini verify stays off in the product (on the earlier driving composite it lost 9/34 true events; not run on the long videos) |
| PB-72 | E13 | Re-tune `fusion.min_event_score` on the held-out long videos (0.5 was chosen on Charades-STA) | S | 3 | Not started | 4 | Follow-up to PB-70; the 0.5 default was checked there but does not separate present from absent prompts on driving, so a threshold sweep is untested; run after PB-71 changes so the threshold is tuned once |

## 3. Definition of Ready (an item may enter a sprint only if…)

- user-visible value and acceptance criteria are written;
- API/DB impact is understood and the contract is documented;
- it can be demoed without a GPU (mock allowed) or the hardware need is explicit;
- dependencies and the backup owner are named.

## 4. Definition of Done

- code reviewed by a second person (or explicitly flagged single-owner in a distributed team);
- tests added and passing; `ruff check` clean; migration included when the schema changes;
- docs/API contract updated in the same change;
- evidence recorded (test output, screenshot path, or smoke-test JSON);
- no secret, private footage or credential committed.

## 5. Grooming notes (2026-11-12)

- **Scope pivot:** the customer's latest answers (CE-2) plus Requirements v1.1 make accounts, global roles,
  datasets, searches and OpenLABEL JSON **MVP Must**. The existing project/action slice is a technical
  prototype; PB-43…PB-66 are the real path to the MVP.
- **Order of work:** authentication and dataset domain first (PB-43…PB-51), then JSON export and the Gemini
  detector (PB-53, PB-57), then the self-hosted engine and KPIs (PB-58…PB-65).
- **Blocking external inputs:** privacy approval for Gemini (R-20), OpenLABEL example (R-25), 12 GB laptop
  access (R-23), test-dataset licence (R-24).
- **Frozen until the MVP works:** PB-67, PB-68, PB-37…PB-40 (multi-model UI, summaries, semantic search).
- Estimates remain provisional; team velocity is still not measured (no capacity data).

## 6. Grooming notes (2026-11-16)

- **Detector decision:** [ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md) makes VideoJev-4B the first real detector (E6/PB-24 superseded, PB-57 Gemini deferred). The engine and `videojev` adapter are integrated; the real-model smoke on the RTX 3070 laptop is pending.
- **Quality:** Charades-STA is reference only (VideoJev was trained on it, so its scores there are in-domain). The SPEC targets were checked on the held-out long-video benchmark (PB-70, 2026-11-22; `video_grounding/docs/EVALUATION.md`): recall 0.86 cooking / 0.47 driving vs 0.85, CCR 0.78 / 0.82 vs 0.85. Cooking recall meets the target only as a point estimate (CI lower bound 0.81); driving misses widely (lateral moves 0/24, overtake 3/12, stop 35/100) and absent prompts give almost as many candidates as present ones (8.4 vs 9.2). Follow-ups: PB-71, PB-72. `min_event_score` was lowered to 0.5 on 2026-11-16 based on Charades-STA (recall 0.690 → 0.771, R1@0.5 0.460 → 0.507); the long-video check kept it but it was not re-tuned (PB-72). Product footage is not measured.
