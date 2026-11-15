# Team Working Agreements

**Status:** provisional · **Date:** 2026-11-05 · **Owner:** Scrum Master (role placeholder)

> No team names, time zones, availability or meeting records have been supplied to the repository. The
> tables below are **placeholders to be filled by the team**; nothing here should be read as a record of a
> meeting that happened.

## 1. Roles

| Role | Person | Backup | Responsibilities |
|---|---|---|---|
| Product Owner | *TBD* | *TBD* | Backlog order, customer questions, acceptance |
| Scrum Master | *TBD* | *TBD* | Ceremonies, artifacts, burndown, impediments |
| Backend owner | *TBD* | *TBD* | API, pipeline, DB, migrations |
| Frontend owner | *TBD* | *TBD* | UI, accessibility, review UX |
| ML / adapter owner | *TBD* | *TBD* | Model selection, adapter, evaluation |
| QA owner | *TBD* | *TBD* | Test plan, acceptance evidence |
| DevOps / docs owner | *TBD* | *TBD* | Installation, deployment, report assembly |

## 2. Capacity (fill before 2026-11-06)

Declared availability per working day, in hours. Planned work must stay at **80–85 %** of this number; the
remainder is contingency for reviews, integration and the unexpected.

| Person | Mon | Tue | Wed | Thu | Fri | Sprint capacity | Planned (≤85 %) | Notes |
|---|---|---|---|---|---|---|---|---|
| *TBD* | | | | | | | | |
| *TBD* | | | | | | | | |
| *TBD* | | | | | | | | |

Known non-working dates: 2026-11-18, 2026-12-25, 2026-12-26, 2027-01-01, 2027-01-06 (public holidays; confirm
personal availability). Weekends are not assumed working time.

## 3. Communication

| Channel | Purpose | Expected response |
|---|---|---|
| Daily async stand-up (written) | yesterday / today / blockers | by 10:00 local |
| Team chat | quick questions, PR links | same working day |
| Pull-request comments | technical review | within 24 h |
| Weekly sync (30 min) | risks, dependencies, demo | fixed slot TBD |
| Supervisor/customer meeting | decisions and feedback | minutes within 24 h |

**Cultural-differences session (2026-10-27):** the course scheduled a mandatory communication session.
**No minutes or conclusions exist in this repository** — if a team member attended, they must add
`docs/meeting-minutes/2026-10-27-cultural-differences.md` with real notes. Do not invent outcomes.

## 4. Engineering workflow

- **Branches:** `main` is always runnable. Work on `feat/<area>-<short>`, `fix/<area>-<short>`.
- **Commits:** imperative subject, body explains *why*; one logical change per commit.
- **Review:** at least one reviewer for code that touches the API contract, schema or security. A distributed
  team may merge with a documented single-owner review and a follow-up review within 24 h.
- **Tests:** every behaviour change needs a test; run `pytest` and `ruff check` before pushing.
- **Contracts:** change `backend/app/schemas.py` and `docs/API_CONTRACTS.md` in the same commit.
- **Migrations:** never edit an applied migration; add a new revision.
- **Docs:** update the implementation log and the affected course artifact in the same week.
- **No secrets, no customer footage, no credentials** in Git. Use `.env`.

## 5. Definition of Ready / Done

See [PRODUCT_BACKLOG.md §3–4](PRODUCT_BACKLOG.md). A task is not "done" without evidence (test output,
screenshot path, or smoke JSON).

## 6. Meetings and artifacts

| Ceremony | When | Output |
|---|---|---|
| Sprint planning | first working day of sprint | Sprint Backlog + goal |
| Daily stand-up | async, every working day | written update |
| Backlog refinement | mid-sprint | ordered backlog, estimated items |
| Sprint review | last day of sprint | review slides with real increment |
| Retrospective | after review | retro slides + 2–3 actions with owners/dates |

Sprint Review and Sprint Retrospective reports are **static slides after every sprint**, including sprints
without an oral presentation (Sprint 5, Sprint 7).

## 7. Decision making

- Technical decisions: the owning role proposes, a second person reviews, record an ADR in `docs/decisions/`.
- Scope changes: Product Owner decides, Scrum Master records the impact on the sprint and the course
  deliverables.
- Course-deadline conflicts: course deadlines win over feature work; escalate to the supervisor early.

## 8. Escalation

1. Blocker > 1 working day → raise in the stand-up and tag the Scrum Master.
2. Course deliverable at risk → Scrum Master informs the supervisor **before** the deadline, not after.
3. Customer requirement ambiguity → Product Owner logs it in `REQUIREMENTS.md §10` and asks the customer.

## 9. Working across sites

- Overlap window for synchronous pairing: **TBD**.
- Every subsystem has a backup owner (table §1) so a site outage does not stop a sprint.
- Recorded decisions, fixtures and smoke scripts replace "it works on my machine" claims.
