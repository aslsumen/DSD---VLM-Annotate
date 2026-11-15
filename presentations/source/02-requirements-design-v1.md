# Requirements & Design v1

*From a vague brief to a tested contract in one sprint*

Course presentation · 2026-11-10 · version 1.0
Upload deadline: Monday 2026-11-09 23:59 (manual course-page upload)
Requirements Definition v1 and Design Description v1 due 2026-11-13 23:59
All numbers in this deck come from this repository; nothing is estimated unless labelled.

---

## 1. What we will cover

*Agenda*

- The problem and the product boundary
- How 28 functional and 14 non-functional requirements were derived
- The two design decisions that shape everything: async jobs and time semantics
- Architecture, data model and API contract
- Review UX, export format, security
- Model evidence and the plan to real inference
- What is actually tested today, and what is still open

## 2. Problem and product boundary

*Context*

**Problem**

- 10–30 minute videos, expensive manual annotation
- Model labels are unverifiable without provenance
- Unlabelled items silently become negatives

**Product boundary**

- AI proposes candidates; humans label
- Async processing, never blocking HTTP
- Dataset export with media + provenance
- Single-view RGB, single team deployment

## 3. How the requirements were built

*Requirements*

| Step | Output | Where |
|---|---|---|
| Brief → user journeys | 4 personas, 7-step workflow | PROJECT_PLAN.md |
| Journeys → functional reqs | 28 FR, MoSCoW, acceptance criteria | REQUIREMENTS.md §4 |
| Quality attributes → NFRs | 14 NFR with targets | REQUIREMENTS.md §5 |
| Each FR → API → test | Traceability matrix | REQUIREMENTS.md §9 |
| Ambiguity → questions | Q-01…Q-05 for the customer | REQUIREMENTS.md §10 |

## 4. Functional requirements at a glance

*Requirements*

| Area | FRs | Must-have behaviour | Status |
|---|---|---|---|
| Projects & actions | FR-01–02 | CRUD, unique names, NL description | Done + tested |
| Video ingestion | FR-03–07 | Limits, signature check, probe, range stream | Done + tested |
| Async jobs | FR-08–13 | 202 enqueue, retries, cancel, idempotency | Done + tested |
| Candidates | FR-14–16 | Timestamps, clips, three boundary families | Done + tested |
| Review | FR-17–21 | TP/FP, unreviewed, corrections, mock label | API done, UI in progress |
| Export | FR-22–26 | Async ZIP, provenance, guards | Done + tested |
| Platform | FR-27–28 | Responsive UI, access control | UI in progress, auth done |

## 5. Non-functional targets

*Requirements*

| NFR | Target | Evidence today |
|---|---|---|
| Async isolation | enqueue < 300 ms, no inference in request | Architecture + 202 test |
| Timestamp correctness | no interval outside the video | 12 unit tests + export checks |
| Upload integrity | SHA-256, atomic write, traversal-proof | 12 storage tests |
| Reproducibility | pinned deps, migrations, manual | lockfile + Alembic run |
| Security | untrusted input, optional bearer | validation + auth tests |
| Maintainability | lint clean, typed contracts | ruff + Pydantic |

## 6. Decision 1 — inference never runs in a request

*Design*

- POST /videos/{id}/jobs writes a row and returns 202 immediately
- A separate worker process claims a job with an atomic conditional UPDATE
- Progress, attempts and structured error codes live on the job
- Transient failures requeue with backoff; retries are idempotent
- Cancellation is queued-only — a running ffmpeg/model call is allowed to finish

_ADR-0001: database-as-queue. No Redis/Celery for a single-host course deployment._

## 7. Job state machine

*Design*

| From | Event | To | Notes |
|---|---|---|---|
| — | enqueue | queued | 202 returned to the browser |
| queued | worker claim | running | atomic UPDATE, attempts+1 |
| running | success | succeeded | progress = 1.0 |
| running | retryable error | queued | backoff, until max_attempts |
| running | attempts exhausted | failed | error_code/message preserved |
| queued | cancel | canceled | never executed |
| failed | manual retry | queued | attempts reset, candidates cleared |

## 8. Decision 2 — time is explicit and layered

*Design*

- Seconds relative to the source video, half-open [start, end)
- proposal: what the model returned (after bound clamping)
- preview: padded window cut to a playable clip — never a label
- corrected: the human edit, stored on the annotation
- final = corrected if present, else proposal
- Every boundary validated: 0 ≤ start < end ≤ duration

_ADR-0002. The export carries all four so a dataset can be audited without our database._

## 9. Decision 3 — unreviewed is a first-class state

*Design*

> No is_negative column exists. A label is an annotation row created by a person. Export excludes everything else unless the caller explicitly asks for unreviewed items.

## 10. Components and responsibilities

*Architecture*

- React/TypeScript UI — projects, upload, polling, review, export
- FastAPI API — validation, auth, range streaming, enqueue
- Worker process — claim, adapter call, ffmpeg clips, archive build
- SQLite/PostgreSQL — 7 tables, Alembic migrations
- Local storage behind an interface — generated keys, traversal guard
- VLMAdapter — mock now; Qwen2.5-VL windowed next; one registry entry to switch

## 11. Seven tables, one invariant each

*Data*

| Table | Purpose | Key invariant |
|---|---|---|
| projects | Organise work | cascade delete cleans media |
| action_definitions | NL prompt | unique name per project |
| videos | Source media | generated key + checksum |
| processing_jobs | Queue + provenance | atomic claim, unique idempotency |
| candidates | Proposals | end > start, unique (job, rank) |
| annotations | Human labels | one per candidate, two verdicts only |
| dataset_exports | Archives | status + item count |

## 12. One contract, shared by UI and worker

*API*

- /projects, /actions, /videos, /jobs, /candidates, /exports under /api/v1
- OpenAPI at /api/docs; Pydantic schemas are the source of truth
- Consistent error envelope: code, message, details
- Range requests on /videos/{id}/stream and /candidates/{id}/clip
- Optional bearer token; health stays public
- 202 for long-running work, 409 for state conflicts

## 13. Reviewing 30 candidates in minutes

*UX*

**Interaction**

- Select candidate → seek source video, load clip
- J = true positive, F = false positive
- ←/→ next/previous, space play/pause
- Filters: all / unreviewed / TP / FP
- Optional correction of start and end
- Auto-advance toggle

**Trust cues**

- Explicit Unreviewed chip and counter
- MOCK banner when no pixels were analysed
- Clip error shown, source-video fallback offered
- Save errors announced, never silent
- Reviewer and note stored with every label

## 14. A dataset that survives without the app

*Export*

- ZIP: manifest.json (schema 1.0), labels.csv, README.txt, clips/
- Per item: proposal, preview, corrected, final, score, notes, reviewer
- Provenance: adapter name/version, mock flag, clamping flag, source checksum
- Refuses to export with nothing reviewed unless explicitly overridden
- Times are seconds in the manifest — no unit ambiguity

## 15. Untrusted by default

*Security*

- Uploads: extension + content type + container signature + size + duration
- Storage keys generated; traversal attempts rejected and tested
- Optional bearer token enforced by middleware on every API route
- Secrets only via environment; data/ and .env git-ignored
- Deletes remove rows and media together

## 16. What the evidence actually supports

*Model*

| Checkpoint | Licence | Temporal grounding | 8 GB fit |
|---|---|---|---|
| Qwen2.5-VL-7B | Apache-2.0 | Card claims segment pinning; mIoU 43.6 listed | No (bf16) |
| Qwen2.5-VL-3B | qwen-research | Same family claims | Yes |
| SmolVLM2-2.2B | Apache-2.0 | None — describe only | Yes (5.2 GB documented) |
| InternVL3.5 / LLaVA-Video / VideoLLaMA3 | Apache/MIT mix | None | Mostly no |

_Sources fetched 2026-11-05; see docs/MODEL_EVALUATION.md. Real inference: NOT RUN yet._

## 17. What is actually verified today

*Evidence*

- **77** — automated tests (56 backend + 21 UI)
- **26/26** — real ffmpeg checks (probe, clips, export, archive)
- **7** — migrated tables (Alembic on a fresh database)
- **0** — fabricated metrics (real model accuracy unmeasured)

_Evidence: docs/evidence/smoke-e2e-20261105-170733.json · docs/TEST_PLAN.md §5_

## 18. Sprint 2 to the MVP gate (2026-11-15)

*Plan*

- 11-06: UI build complete, guidelines downloaded, capacity filled
- 11-09: this deck uploaded by 23:59
- 11-10: presentation; feedback into backlog
- 11-12: Requirements v1 and Design v1 frozen
- 11-13: real 10–30 minute video validated end-to-end
- 11-15: MVP gate evidence, Sprint 2 review and retrospective

## 19. Risks and decisions we need

*Open*

- Guidelines still behind login → decks are provisional (R-01)
- Real inference feasibility on 8 GB VRAM (R-03)
- Capacity and supervisor access still unconfigured (R-04, R-12)
- Q-01 clip tightness · Q-02 action types · Q-03 max duration
- Q-04 target dataset format · Q-05 uncertain labels
- Decision needed: acceptable licence for distributed weights
