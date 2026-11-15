# Status — Sprint 2 close, Sprint 3 plan

*What we built, what the customer changed, and what comes next*

Course presentation · 2026-11-17 · version 1.0
Upload deadline: Monday 2026-11-16 23:59 (manual course-page upload)
Prepared 2026-11-15 from repository evidence — no unverified claims

---

## 1. Where we are

*Position*

- Sprint 2 closed on 2026-11-15: a tested technical prototype exists
- Sprint 3 runs 2026-11-16 → 2026-11-29; Alpha presentation on 2026-12-01
- The customer's 9 Nov answers expand the MVP: accounts, roles, datasets, searches, JSON
- Requirements/Design v1.1 PDFs delivered to the team; repo copies updated to v1.2
- The prototype does not yet meet the v1.1 MVP; this deck states the gap plainly

## 2. Sprint 2 by the numbers

*Evidence*

- **56** — backend tests (pytest, all green)
- **21** — UI tests (vitest, build clean)
- **26/26** — real ffmpeg checks (15 Nov smoke run)
- **0** — measured model KPIs (no real detector yet)

_Test counts are verifiable in docs/TEST_PLAN.md; the smoke JSON is in docs/evidence/._

## 3. What the prototype can do today

*Increment*

| Capability | State |
|---|---|
| Create projects, define NL action prompts | Working |
| Upload MP4/MOV/WebM, probe, stream with Range | Working |
| Asynchronous jobs, retries, cancel, progress | Working |
| Timestamped candidates + real preview clips | Working |
| Review TP/FP, correct timestamps, unreviewed state | Working |
| Export ZIP with manifest, CSV, clips, provenance | Working (wrong target format) |
| Responsive browser UI | Working (desktop, 375 px) |
| Real zero-shot detection | Missing — mock labelled |

## 4. Requirements & Design v1 (team v1.1 + repo v1.2)

*Documents*

| Area | Content |
|---|---|
| Requirements | 27 functional (DS/PR/DET/REV/EXP/SRCH/USR), 14 NFR, 7 user stories |
| Engine | 13 engine requirements, proposed KPIs (recall ≥0.85, R@IoU0.5 ≥0.70) |
| Roles | Administrator, Dataset Administrator, Annotator — global, invited by email |
| Design | Target architecture, data model, search flow, detection engine, JSON proposal |
| Traceability | Each requirement mapped to code/tests; implementation status honest |

## 5. What the customer changed on 9 Nov

*Customer*

- Dataset Administrators may create, upload, export and invite users
- Roles are global; a Dataset Admin annotates elsewhere with a separate Annotator account
- Accounts are email-only invitations: no username, optional organization
- Workflow: upload many videos, run prompts later, annotators review later
- Export is OpenLABEL-based JSON; one action may have several intervals
- Video summaries and tags are explicitly outside the MVP

## 6. Prototype vs v1.1 MVP

*Gap*

**Already reusable**

- Upload, probe, range streaming
- Job queue + worker + retries
- Candidate model (raw/final times)
- Review API and UX
- Clip extraction and provenance
- Test harness and error envelope

**Still to build**

- Users, global roles, invitations, sessions
- Dataset entity + assignments
- Search over all videos of a dataset
- OpenLABEL JSON export
- Real detector (Gemini/VideoJev)
- Signed media URLs, pagination, packaging

## 7. Sprint 3 — 16 → 29 Nov

*Plan*

| Workstream | Goal |
|---|---|
| Accounts & access | Users, global roles, invitations, sessions, sign-out/expiry/lockout |
| Dataset & search domain | Dataset entity, assignments, search fan-out over videos |
| JSON export | OpenLABEL-based schema with intervals, reviewer, provenance |
| Detection engine | Gemini backend first; VideoJev-4B self-hosted second |
| UI | Sign-in, invitation, dataset page, cross-video review, export |

## 8. How detection will be built

*Engine*

- One `GroundingBackend` interface; Gemini and VideoJev behind it
- 30 s windows, 20 s stride, 0.5 FPS coarse scan, 1 FPS refinement
- Fuse score curves on one timeline; hysteresis 0.25/0.15
- Completeness flags: video edge, window edge, sparse sampling, coverage gap
- Self-hosted by default for customer footage; cloud API only with written approval
- Measure KPIs on Charades-STA / TimeLens before promising accuracy

## 9. Sprint 3 exit criteria (Alpha, 29 Nov)

*Gate*

| Criterion | Target |
|---|---|
| Sign in, roles, invitation flow | Works end-to-end with two roles |
| Dataset + search over several videos | Search returns candidates from all videos |
| JSON export | Contains accepted annotations, intervals, provenance |
| Real detector on test videos | Gemini or VideoJev measured on public data |
| KPI report | Recall/R@IoU/precision on a labelled sample |
| Prototype testable | Documented limitations, no fake claims |

## 10. Blockers and risks

*Risks*

| Risk | Response |
|---|---|
| No privacy approval for Gemini on face videos | Test data only; self-host for customer data |
| Gemini key expired/leaked | Request a new key securely; env var only |
| OpenLABEL example still missing | Send schema proposal by 17 Nov; confirm before coding |
| 12 GB vs 24 GB VRAM | Quantised 4B + low-VRAM profile; API fallback |
| No capacity data | Fill table before Sprint 3 planning |

## 11. Decisions and dates

*Ask*

- ☐ Upload this deck by Mon 16 Nov 23:59 (presentation 17 Nov)
- ☐ Confirm 10/13 Nov submissions and record evidence
- ☐ Answer: privacy for Gemini, reviewer attribution, dataset meaning, JSON fields
- ☐ Decide hosting/compute: 12 GB laptop, GPU server or cloud API
- ☐ Alpha gate 29 Nov; presentation 1 Dec; Acceptance Test Plan due 25 Dec
