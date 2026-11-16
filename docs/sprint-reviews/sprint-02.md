# Sprint 2 Review — facts only

**Sprint:** 2 (2026-11-02 → 2026-11-15) · **Review written:** 2026-11-15
**Type:** static presentation source → `presentations/sprint-02-review.pptx`

> No Sprint 2 review meeting is recorded in this repository, and no supervisor/customer feedback from the
> 10 Nov presentation or the 13 Nov submissions was captured. This document summarises verifiable outcomes and
> marks the unknowns explicitly.

## 1. Sprint goal

From `docs/SPRINT_BACKLOG.md`: deliver the Requirements & Design presentation and v1 documents, keep a runnable
vertical slice, and keep the Scrum artifacts living. Mocked inference was explicitly acceptable if labelled.

## 2. Delivered increment (verified 2026-11-15)

| Item | State | Evidence |
|---|---|---|
| Media pipeline: upload, probe, range streaming, real clips | Working | 56 backend tests; smoke 26/26 |
| Async jobs: queue, worker, retries, cancel, idempotency | Working | `test_flow.py`, `test_worker.py` |
| Candidates and review: TP/FP, unreviewed, corrections | Working | API tests; UI E2E reported |
| Responsive UI | Working | build clean; 21 tests; 375 px |
| ZIP export with manifest/CSV/clips/provenance | Working, wrong target format | `test_flow.py`; target is OpenLABEL JSON |
| Mock detector, labelled | Working | MOCK banner + `provenance.mock` |
| Requirements/Design documents | v1.1 PDFs + repo v1.2 | `docs/inputs/2026-11-12/`, `docs/REQUIREMENTS.md` |
| Course deliverables register and briefs | Done | `docs/course/`, `docs/CLIENT_MEETING_BRIEF_2026-11-13.md` |

**Measured at close:** 56 backend tests passed · 21 UI tests passed · ruff clean · real-ffmpeg smoke 26/26
(`docs/evidence/smoke-e2e-20261115-180704.json`) · migration verified earlier on a fresh SQLite database.

## 3. Not delivered / failed

- **v1.1 MVP scope:** accounts, global roles, invitations, datasets, searches and OpenLABEL JSON are missing.
- **Real detection:** no Gemini/VideoJev inference; KPIs unmeasured.
- **Real long video:** only synthetic 2-minute footage tested.
- **Submission evidence:** no record of the 10 Nov presentation or the 13 Nov document submission.
- **Supervisor access:** living artifacts are local files.
- **Capacity/names:** still not supplied.

## 4. Demo / testability

The prototype is runnable on a clean Windows machine with the installation manual (API + worker + built UI) and
can execute the full loop with mock candidates. It is **testable**, but it is **not** the v1.1 MVP. Verdict for
the course gate: **PASS as a technical prototype; FAIL against the v1.1 MVP; re-baseline with the supervisor.**

## 5. Scope change during the sprint

The customer's 9 Nov answers added: Dataset Administrators may invite users; global roles; email-only
invitations; non-continuous workflow; OpenLABEL JSON with multiple intervals; summaries/tags outside the MVP;
Gemini API access. Impact and plan: `docs/CLIENT_MEETING_BRIEF_2026-11-13.md`.

## 6. Feedback received

**None recorded.** If the 10 Nov presentation produced feedback, or the 13 Nov client meeting produced answers,
a team member must add them to `docs/customer/CUSTOMER_DECISIONS.md`; they have not been invented.

## 7. Backlog movement

77 of 82 provisional story points marked done; 2 blocked (human actions); 3 open (real long-video validation,
carried to Sprint 3). See `docs/SPRINT_BACKLOG.md` and `docs/SPRINT_BURNDOWN.md`.

## 8. Risks carried into Sprint 3

R-19/R-22 (scope pivot and timeline), R-20 (Gemini privacy approval), R-21 (key expiry), R-23 (VRAM), R-24
(dataset licences), R-25 (OpenLABEL example missing), R-26 (detection quality). Full register:
`docs/RISK_REGISTER.md`.
