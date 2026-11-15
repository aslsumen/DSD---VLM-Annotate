# Week 03 Report — 2026-11-09 → 2026-11-15 (Sprint 2 close)

**Sprint:** 2 (2026-11-02 → 2026-11-15) · **Written:** 2026-11-15 · **Author:** implementation harness
**Team capacity:** still not supplied

> Final report for the week. Items not executed are marked `NOT RUN`/`UNVERIFIED`; no uploads, feedback or
> measurements are invented.

## 1. Goal

Deliver the Requirements & Design presentation and the two v1 documents, keep the prototype testable, close
Sprint 2 on 2026-11-15, and prepare the Status presentation for 2026-11-17.

## 2. Done this week

| Item | Status | Evidence |
|---|---|---|
| Customer answers (9 Nov) analysed and transcribed | **Done** | `docs/customer/CUSTOMER_DECISIONS.md` |
| Client meeting brief for 13 Nov (English, DOCX/PDF) | **Done** | `docs/CLIENT_MEETING_BRIEF_2026-11-13.*` |
| Requirements Definition aligned to v1.1 + answers | **Done (repo v1.2)** | `docs/REQUIREMENTS.md` |
| Design Description aligned to v1.1 + answers | **Done (repo v1.2)** | `docs/DESIGN_DESCRIPTION.md` |
| Architecture / API / DB reframed as target + current | **Done** | `docs/ARCHITECTURE.md`, `API_CONTRACTS.md`, `DATABASE_SCHEMA.md` |
| As-built baseline preserved | **Done** | `docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md` |
| Model evaluation updated (Gemini, VideoJev, datasets) | **Done** | `docs/MODEL_EVALUATION.md` |
| Backlog/risks extended with the new MVP scope | **Done** | PB-43…PB-69, R-19…R-26 |
| **Sprint 2 review deck** | **Done 2026-11-15** | `presentations/sprint-02-review.pptx` (11 slides) |
| **Sprint 2 retrospective deck** | **Done 2026-11-15** | `presentations/sprint-02-retrospective.pptx` (8 slides) |
| **Status deck for 17 Nov** | **Done 2026-11-15** | `presentations/03-status.pptx` (12 slides) |
| Sprint backlog closed and burndown finalised | **Done** | `docs/SPRINT_BACKLOG.md`, `docs/SPRINT_BURNDOWN.md` |

## 3. Verification at sprint close (2026-11-15, actual)

| Check | Command | Result |
|---|---|---|
| Backend tests | `.\.venv\Scripts\python.exe -m pytest -q` | **56 passed** |
| Lint | `ruff check app tests` | **clean** |
| Real ffmpeg end-to-end | `scripts\smoke_e2e.py` | **26/26 checks** → `docs/evidence/smoke-e2e-20261115-180704.json` |
| UI build | `npm run build` | **PASS** (285.93 kB JS / 18.34 kB CSS, gzip 86.49 / 4.44) |
| UI tests | `npm test` | **21 passed** |

## 4. Not done / unverified

| Item | Status | Why |
|---|---|---|
| Requirements & Design presentation (10 Nov) evidence | **UNVERIFIED** | No upload/presentation record in the repo |
| Requirements v1 + Design v1 submission (13 Nov) | **UNVERIFIED** | No submission record; v1.1 PDFs exist |
| 13 Nov client meeting answers | **NOT RECORDED** | No notes in the repo; must not be invented |
| Real 10–30 min video validation | **NOT RUN** | Carried to Sprint 3 |
| Accounts/roles/datasets/searches/JSON | **NOT IMPLEMENTED** | Scope added 9 Nov; moves to Sprint 3 |
| Supervisor access, team capacity, guidelines | **OPEN** | Human actions |

## 5. Sprint 2 outcome

- **Testable technical prototype: PASS.** The full loop runs locally with mock candidates, real clips and
  tested review/export.
- **v1.1 MVP: FAIL / re-baseline.** Accounts, global roles, invitations, datasets, searches and OpenLABEL JSON
  are not built; no real detector.
- **77 of 82 provisional story points done**, 2 blocked (human), 3 carried over.
- Recommendation: agree with the supervisor that the 15 Nov gate is met by a testable prototype whose
  limitations are explicit, and move the v1.1 MVP scope to Sprint 3–4.

## 6. Deadlines next week

| Date | Item |
|---|---|
| **2026-11-16 23:59** | Upload the Status deck (manual course-page action) |
| 2026-11-17 | Status presentation; send JSON schema proposal to the customer |
| 2026-11-16 → 29 | Sprint 3: accounts/roles, dataset/search, JSON export, detector |
| 2026-11-29 | Sprint 3 gate: Alpha prototype testable |
| 2026-12-01 | Alpha presentation (upload by 2026-11-30 23:59) |

## 7. Dependencies for Sprint 3

1. Client answers on privacy, reviewer attribution, dataset meaning and JSON fields.
2. Gemini key status (redeemed or replaced) and privacy approval.
3. Decision on compute/hosting (12 GB laptop, GPU server or API).
4. Capacity and ownership data; supervisor access.
5. The customer's OpenLABEL example.
