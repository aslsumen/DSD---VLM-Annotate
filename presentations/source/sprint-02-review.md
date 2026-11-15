# Sprint 2 Review

*A tested prototype, a changed scope, and an honest verdict*

Static report slides · Sprint 2: 2026-11-02 → 2026-11-15
Produced 2026-11-15 from repository evidence and test runs
Evidence: docs/evidence/smoke-e2e-20261115-180704.json

---

## 1. What we committed to

*Sprint goal*

- Deliver the Requirements & Design presentation and the v1 documents
- Build a runnable, testable vertical slice: upload → async job → candidates → review → export
- Keep Scrum artifacts living and supervisor-accessible
- Explicitly acceptable for inference to be mocked at this stage, if labelled

_Sprint 2 goal recorded in docs/SPRINT_BACKLOG.md._

## 2. What was delivered

*Delivery*

| Increment | State | Evidence |
|---|---|---|
| Media pipeline: upload, probe, range streaming, real clips | Working | 56 backend tests + smoke |
| Async jobs: queue, worker, retries, cancel, idempotency | Working | test_flow / test_worker |
| Candidates + review: TP/FP, unreviewed, corrections | Working | API tests + UI E2E |
| Responsive web UI | Working | build + 21 tests, 375 px |
| Dataset export (ZIP + manifest + CSV) | Working, wrong format | target is OpenLABEL JSON |
| Mock detector, clearly labelled | Working | no pixels analysed |

## 3. Verified at sprint close

*Evidence*

- **56** — backend tests (pytest, all passing)
- **21** — UI tests (vitest, build clean)
- **26/26** — real ffmpeg checks (smoke run 2026-11-15)
- **0** — measured model KPIs (real inference not wired)

_Latest smoke evidence: docs/evidence/smoke-e2e-20261115-180704.json_

## 4. Is the Sprint 2 increment testable?

*Gate*

- Yes as a technical prototype: a reviewer can run the full loop locally
- No as the v1.1 MVP: no accounts, roles, datasets, searches, OpenLABEL JSON or real detection
- Limitation stated in the app (MOCK banner) and in every document
- Real 10–30 min footage still not validated
- Verdict: testable prototype, not MVP — re-baseline with the supervisor

## 5. What changed mid-sprint

*Scope*

| Customer answer (9 Nov) | Impact |
|---|---|
| Dataset Administrators may invite users | Permission matrix and USR-4/USR-5 updated |
| Roles are global | Authorization model simplified; open question closed |
| Email-only accounts | No username; invitation flow fixed |
| Workflow is upload-many, search-later, review-later | Search must fan out over all videos |
| JSON based on OpenLABEL; multiple intervals per action | Export must be rewritten |
| Gemini API key supplied | API detector possible; privacy approval needed |
| Summaries/tags outside the MVP | EXP-3/EXP-4/SRCH-1 downgraded to Could |

## 6. Requirements and design v1

*Documents*

- Team v1.1 PDFs archived in docs/inputs/2026-11-12/
- Repository working copies updated to v1.2 with the 9 Nov answers
- 27 functional requirements, 14 non-functional, 13 engine requirements, KPIs
- Design: target architecture, auth/roles, dataset/search model, engine, JSON proposal
- Submission on 13 Nov: no evidence recorded — human confirmation required

## 7. Sprint backlog completion

*Plan*

| Status | Story points | Notes |
|---|---|---|
| Done | 77 | backend, UI, tests, docs, decks, brief, sprint close |
| Blocked (human) | 2 | team capacity, supervisor access, guideline download |
| Open | 3 | real 10–30 min video validation |
| Total | 82 | provisional estimates, no capacity data |

_Burndown: docs/SPRINT_BURNDOWN.md · 74 SP were burned in the 5 Nov session; 3 SP at close._

## 8. What is at risk now

*Risks*

- R-19/R-22: the v1.1 MVP needs auth, roles, datasets, searches and JSON — not built yet
- R-20: no written approval to send face videos to Gemini
- R-21: Gemini key may have expired before redemption
- R-25: customer's OpenLABEL example still missing
- R-23: 12 GB VRAM offered vs 24 GB assumed for quantised inference

## 9. Sprint 2 outcome

*Verdict*

| Gate | Result |
|---|---|
| Requirements & Design presentation (10 Nov) | Deck ready; upload/presentation evidence unrecorded |
| Requirements v1 + Design v1 (13 Nov) | v1.1 PDFs exist; submission unverified |
| Prototype testable (15 Nov) | PASS as technical prototype (mock) |
| MVP scope of v1.1 | FAIL / re-baseline — not implemented |
| Living artifacts accessible | FAIL — local files only |

## 10. Immediate follow-ups

*Next*

- ☐ Upload the Status deck by 16 Nov 23:59 for the 17 Nov presentation
- ☐ Record real evidence for the 10 and 13 Nov submissions
- ☐ Capture the 13 Nov client answers (privacy, reviewer, dataset, JSON) in the repo
- ☐ Redeem or replace the Gemini key; never commit it
- ☐ Start Sprint 3 with auth/roles + Dataset/Search domain
