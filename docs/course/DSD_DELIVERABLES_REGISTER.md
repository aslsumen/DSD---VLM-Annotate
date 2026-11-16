# DSD Deliverables Register — VLM Annotate

Single source of truth for course deliverables: required **type**, due date, owner, current status and the
evidence that actually exists. Status vocabulary: `DONE` · `IN PROGRESS` · `DRAFT` · `NOT STARTED` ·
`OVERDUE` · `BLOCKED` · `NOT DUE`.

**Last updated:** 2026-11-15 (Sprint 2 closed). **Owner column uses role placeholders** — replace them in the
first team meeting. **Scope update:** the customer's latest answers (see `docs/customer/CUSTOMER_DECISIONS.md`)
extend the MVP; the submitted PDFs are the team's v1.1 copies in `docs/inputs/2026-11-12/`, while the repository
working copies are v1.2.

## 1. Deliverables

| # | Deliverable | Required type | Due (23:59) | Owner (role) | Status | Evidence / location | Course-page upload |
|---|---|---|---|---|---|---|---|
| D-01 | Project Plan v1 | **Versioned presentation slides** | 2026-11-02 | Product Owner + Scrum Master | **OVERDUE (built 2026-11-05)** | `presentations/01-project-vision-plan-v1.pptx` + `presentations/source/01-project-vision-plan-v1.md`; supporting text `docs/PROJECT_PLAN.md` | **NOT UPLOADED.** No human confirmation. Must be uploaded and reported to the supervisor. |
| D-02 | Requirements Definition v1 | Versioned document | 2026-11-13 | Requirements owner | **DUE PASSED — submission not recorded; v1.1 PDF + repo v1.2 exist** | `docs/REQUIREMENTS.md`; PDF in `docs/inputs/2026-11-12/` | n/a (document; confirm delivery channel) |
| D-03 | Design Description v1 | Living document / tool content | 2026-11-13 | Architect + UI owner | **DUE PASSED — submission not recorded; v1.1 PDF + repo v1.2 exist** | `docs/DESIGN_DESCRIPTION.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/DATABASE_SCHEMA.md` | n/a |
| D-04 | Product Backlog | Living, supervisor-accessible | continuous | Product Owner | **IN PROGRESS — local file only; supervisor access NOT configured** | `docs/PRODUCT_BACKLOG.md` | n/a — **action:** create shared board or grant read access |
| D-05 | Sprint Backlog | Living, supervisor-accessible | continuous | Scrum Master | **IN PROGRESS — local file only** | `docs/SPRINT_BACKLOG.md` (Sprint 2) | n/a — **action:** shared access |
| D-06 | Sprint Burndown Chart | Living, supervisor-accessible | continuous | Scrum Master | **IN PROGRESS — table + generated SVG** | `docs/SPRINT_BURNDOWN.md`, `docs/burndown/sprint-02.svg` | n/a — **action:** shared access |
| D-07 | Sprint Review Report (Sprint 1) | Static presentation slides | after 2026-11-01 | Scrum Master | **DONE (late), not uploaded** | `presentations/sprint-01-review.pptx` | manual upload required |
| D-08 | Sprint Retrospective Report (Sprint 1) | Static presentation slides | after 2026-11-01 | Scrum Master | **DONE (late), not uploaded** | `presentations/sprint-01-retrospective.pptx` | manual upload required |
| D-09 | Sprint Review + Retrospective (Sprints 2–7) | Static slides after every sprint | 2026-11-15, 11-29, 12-13, 12-27, 2027-01-10, 01-17 | Scrum Master | **Sprint 2 decks produced 2026-11-15; Sprint 1 decks produced late, not uploaded** | `presentations/sprint-02-review.pptx`, `sprint-02-retrospective.pptx` | manual upload evidence needed |
| D-10 | Acceptance Test Plan | **Static presentation slides** | 2026-12-25 | QA owner | **NOT STARTED** (planned 2026-12-22/23) | will be `presentations/acceptance-test-plan.pptx` | manual upload required |
| D-11 | Acceptance Test Report | **Static presentation slides** | 2027-01-04 | QA owner | **NOT STARTED** (planned 2026-12-29/30) | will be `presentations/acceptance-test-report.pptx` | manual upload required |
| D-12 | Deployment / installation documentation | Static document | 2027-01-17 | DevOps owner | **DRAFT** | `docs/INSTALLATION_MANUAL.md` | n/a |
| D-13 | Final Report (≤ 20 pages) | Static document | 2027-01-17 | All owners | **NOT STARTED** (scaffolded outline only at the end of Sprint 6) | will be `docs/FINAL_REPORT.md` + PDF | n/a |
| D-14 | Final product + source | Product / repository | 2027-01-17 | All owners | **IN PROGRESS** | `backend/`, `frontend/`, `scripts/`, this docs tree | n/a |
| D-15 | Requirements & Design presentation | Presentation slides | uploaded by **2026-11-09**, presented 2026-11-10 | Architect + Requirements owner | **NO EVIDENCE RECORDED** — deck exists (20 slides); upload/presentation outcome not confirmed in repo | `presentations/02-requirements-design-v1.pptx` | verify with the team; record evidence |
| D-16 | Status presentation | Presentation slides | uploaded by **2026-11-16**, presented 2026-11-17 | Scrum Master | **READY — 12 slides, PPTX + Markdown source** | `presentations/03-status.pptx` | **manual upload by Mon 2026-11-16 23:59** |

## 2. Presentation upload checklist (manual human action every time)

| Presentation | Deadline | Deck path | Owner | Uploaded? | Evidence/link | Supervisor notified? |
|---|---|---|---|---|---|---|
| Intro / Vision / Plan (2026-11-03) | 2026-11-02 23:59 | `presentations/01-project-vision-plan-v1.pptx` | TBD | **NO — MISSED** | none | **NO** |
| Requirements & Design (2026-11-10) | **2026-11-09 23:59** | `presentations/02-requirements-design-v1.pptx` | TBD | no | — | no |
| Status (2026-11-17) | 2026-11-16 23:59 | TBD | TBD | not due | — | — |
| Alpha (2026-12-01) | 2026-11-30 23:59 | TBD | TBD | not due | — | — |
| Beta (2026-12-15) | 2026-12-14 23:59 | TBD | TBD | not due | — | — |
| Final (2027-01-12) | 2027-01-11 23:59 | TBD | TBD | not due | — | — |

> The harness cannot log in to the course page and will never mark an upload as done without a human
> confirmation. Paste the confirmation link (or a screenshot path) into the "Evidence/link" cell.

## 3. Immediate actions (as of 2026-11-15)

| Action | Owner | Deadline | Blocking? |
|---|---|---|---|
| **Upload the Status deck (D-16)** | Scrum Master | **2026-11-16 23:59** | yes — presentation 11-17 |
| Record evidence for the 10 Nov presentation and 13 Nov submissions | Scrum Master | 2026-11-17 | yes — compliance evidence |
| Write the 13 Nov client answers into `CUSTOMER_DECISIONS.md` | Product Owner | 2026-11-17 | yes — blocks JSON/auth design |
| Start Sprint 3: accounts/roles, dataset/search domain, Gemini detector spike | Team | 2026-11-16 | yes — Alpha gate 11-29 |
| Fill capacity, roles, supervisor access | Product Owner | 2026-11-18 | yes |
| Validate a real 10–30 min video and record evidence | QA | 2026-11-20 | no, but closes Sprint 2 carry-over |
| Redeem/replace the Gemini key securely; never commit it | Backend owner | 2026-11-16 | yes — R-21 |
| Download the official guideline files (401 wall) | Team member with FER AAI | 2026-11-16 | yes — R-01 |
| Send the customer the JSON schema proposal | Architect | 2026-11-17 | yes — EXP-1 |
