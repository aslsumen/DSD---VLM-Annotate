# DSD Course Calendar — VLM Annotate (2026/2027)

**Status:** transcribed from the official course-news text supplied to the team on **2026-10-22/23**.
**Last verified:** 2026-11-05. **Re-verify every week:** newer course-webpage announcements override this file.

> The course materials folder `Guidelines (SCRUM, Presentations)` is **not** in this repository and is not
> publicly reachable (see [OFFICIAL_GUIDELINES_CHECKLIST.md](OFFICIAL_GUIDELINES_CHECKLIST.md)).
> Dates below come from the news text only; document/slide *content* rules remain to be confirmed against
> the official guideline files.

## 1. Fixed sprints and scheduled presentations

| Sprint | Start | End | Scheduled presentation | MVP/prototype gate |
|---|---|---|---|---|
| 1 | 2026-10-19 | 2026-11-01 | Intro / Vision / Plan — **Tue 2026-11-03** | none (explicitly not required) |
| 2 | 2026-11-02 | 2026-11-15 | Requirements & Design — **Tue 2026-11-10**; Status — **Tue 2026-11-17** | **Sun 2026-11-15** |
| 3 | 2026-11-16 | 2026-11-29 | Alpha prototype — **Tue 2026-12-01** | **Sun 2026-11-29** |
| 4 | 2026-11-30 | 2026-12-13 | Beta prototype — **Tue 2026-12-15** | **Sun 2026-12-13** |
| 5 | 2026-12-14 | 2026-12-27 | none scheduled | **Sun 2026-12-27** |
| 6 | 2026-12-28 | 2027-01-10 | Final — **Tue 2027-01-12** | **Sun 2027-01-10** |
| 7 | 2027-01-11 | 2027-01-17 | none listed | final product + static documents **2027-01-17** |

All oral presentations fall on a **Tuesday**. The Sprint 2 slot therefore carries two presentations
(Requirements & Design on Nov 10, Status on Nov 17), which straddles the Sprint 2 end.

## 2. Upload rule and derived deadlines

> Presentations must be uploaded to the DSD course webpage **no later than Monday 23:59** before the
> scheduled presentation.

| Presentation | Presentation date | Hard upload deadline (Mon 23:59) | Deck (repository path) | Uploaded to course page? |
|---|---|---|---|---|
| Intro / Vision / Plan | 2026-11-03 | **2026-11-02 23:59** | `presentations/01-project-vision-plan-v1.pptx` | **NO — MISSED.** No evidence in repo; human must upload and confirm. |
| Requirements & Design | 2026-11-10 | **2026-11-09 23:59** | `presentations/02-requirements-design-v1.pptx` | NOT YET — ready in repo; manual upload required. |
| Status | 2026-11-17 | **2026-11-16 23:59** | to be built Week 4 | not yet |
| Alpha prototype | 2026-12-01 | **2026-11-30 23:59** | to be built Week 5 | not yet |
| Beta prototype | 2026-12-15 | **2026-12-14 23:59** | to be built Week 7 | not yet |
| Final | 2027-01-12 | **2027-01-11 23:59** | to be built Week 12 | not yet |

A file in Git is **not** proof of course-page upload. Only a human-confirmed upload with a link/screenshot
counts, and it must be recorded in
[DSD_DELIVERABLES_REGISTER.md](DSD_DELIVERABLES_REGISTER.md).

## 3. Statutory deadlines

| Deliverable | Type | Due (23:59) | Working deadline we plan for |
|---|---|---|---|
| Project Plan v1 | **versioned presentation slides** (not a Markdown plan) | 2026-11-02 | **overdue** — deck built 2026-11-05 |
| Requirements Definition v1 | versioned document | 2026-11-13 | 2026-11-12 |
| Design Description v1 | living document / maintained in a suitable tool | 2026-11-13 | 2026-11-12 |
| Acceptance Test Plan | **static presentation slides** | 2026-12-25 | **2026-12-23** (before Christmas) |
| Acceptance Test Report | **static presentation slides** | 2027-01-04 | **2026-12-30** or 2027-01-03 at the latest |
| Installation / deployment documentation | static document | 2027-01-17 | 2027-01-15 |
| Final Report (≤ 20 pages) | static document | 2027-01-17 | 2027-01-15 |
| Final product (source, install assets) | product | 2027-01-17 | 2027-01-15 |

Living deliverables with no single deadline: Product Backlog, Sprint Backlog, Sprint Burndown Chart
(continuously maintained, supervisor-accessible), and a Sprint Review + Sprint Retrospective report after
**every** sprint — including Sprint 5 and Sprint 7, which have no oral presentation.

## 4. Non-working days and availability assumptions

These are Croatian public holidays in the project window. **They are not yet confirmed team absences** —
each person must confirm availability before work is planned on or around them.

| Date | Day | Note |
|---|---|---|
| 2026-11-01 | Sunday | All Saints' Day (public holiday) |
| 2026-11-18 | Wednesday | Remembrance Day (public holiday) — inside Sprint 3 |
| 2026-12-25 | Friday | Christmas Day — Acceptance Test Plan deadline falls on this date |
| 2026-12-26 | Saturday | St Stephen's Day |
| 2027-01-01 | Friday | New Year's Day |
| 2027-01-06 | Wednesday | Epiphany — inside Sprint 6 |

Planning rules that follow from the calendar:

1. **No work is assumed** on 2026-12-25, 2026-12-26, 2027-01-01 or 2027-01-06. The Acceptance Test Plan
   is therefore planned for **2026-12-22/23**, six days before its statutory deadline.
2. The Acceptance Test Report is planned for **2026-12-29/30** (before the New Year break) with
   2027-01-03 as the reserve day, one day before the statutory deadline.
3. Sprint 5 (Dec 14–27) and Sprint 6 (Dec 28–Jan 10) each contain holidays. Their planned capacity must be
   reduced; the burndown must not assume full weeks.
4. Exam periods, travel and part-time work are **unknown**. The workload table in
   [TEAM_WORKING_AGREEMENTS.md](../TEAM_WORKING_AGREEMENTS.md) uses role placeholders until each person
   enters real availability.

## 5. Where each rule came from

| Rule | Source | Verified? |
|---|---|---|
| Sprint dates, presentation dates, upload rule, deliverable dates and types, MVP gates | Course-news text supplied 2026-10-22/23 (also transcribed in `DSD_COURSE_CALENDAR_AND_DELIVERABLE_REGISTER.md` at repo root) | Yes — supplied by the team |
| Course exists for 2026/2027 at `/en/course/rrpp_a` | Public FER course page | Yes — fetched 2026-11-05 |
| Detailed Scrum/document/presentation requirements | `Guidelines (SCRUM, Presentations)` files | **NO — login wall; must be obtained manually** |

If a newer announcement changes a date, update this file, the deliverables register and the affected
weekly report in the same commit, and tell the team in the daily stand-up.
