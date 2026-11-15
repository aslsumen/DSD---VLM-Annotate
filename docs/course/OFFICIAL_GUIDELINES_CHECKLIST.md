# Official Guidelines Checklist — what we have actually inspected

**Purpose:** keep an evidence-based list of which official DSD instructions the team has really read, so that
no one mistakes the generic plan for the official rulebook.

**Last updated:** 2026-11-05 by the implementation harness.

## 1. Inspection status

| # | Item | Location | Status | Evidence / what we know |
|---|---|---|---|---|
| 1 | DSD course-news text (2026-10-22/23) | supplied to the team; transcribed at repo root `DSD_COURSE_CALENDAR_AND_DELIVERABLE_REGISTER.md` | **INSPECTED** | Dates, deliverable types, upload rule, MVP gates |
| 2 | Public course page for 2026/2027 | <https://www.fer.unizg.hr/en/course/rrpp_a> | **INSPECTED (metadata only)** | Page confirms the course runs in 2026/2027. Course slug is `rrpp_a`, **not** `dsd` (`/en/course/dsd` returns 404) |
| 3 | `Guidelines (SCRUM, Presentations)` folder | `/predmet/rrpp_a/materijali` (and Croatian twin) | **BLOCKED — HTTP 401 login wall** | Neither the folder nor the three files is publicly reachable as of 2026-11-05 |
| 4 | `DSD SCRUM elements` | inside folder #3 | **NOT INSPECTED** | Mandatory/optional Scrum elements, roles, ceremony rules — **unknown** |
| 5 | `DSD Documentation Guidelines` | inside folder #3 | **NOT INSPECTED** | Required document structure, page limits, appendix/reference counting — **unknown** |
| 6 | `DSD Presentation Guidelines` | inside folder #3 | **NOT INSPECTED** | Slide sections, whether review and retrospective may share a deck, formatting — **unknown** |
| 7 | Evaluation sheet / final questionnaire templates | linked from the public FER pages | **NOT INSPECTED** | PDFs were not retrievable by the research tool; a human must download them |

**Consequence:** every slide deck in `presentations/` uses a *provisional* structure marked as such. It is a
superset of what the course news requires, but it has **not** been validated against the real presentation
guidelines. This is tracked as risk R-01 and as a blocking human action.

## 2. Human action required (blocking, cannot be automated)

| Action | Who | By when | Why |
|---|---|---|---|
| Log in to FER AAI and download the three files + evaluation templates from `/predmet/rrpp_a/materijali` | A team member with FER credentials (owner TBD) | **2026-11-06** (before the Nov 10 deck is finalised) | Only then can decks/documents be validated |
| Place the files under `docs/course/guidelines/` (or share a read-only link) | same person | 2026-11-06 | So the whole distributed team can inspect them |
| Reply in the team channel with "guidelines downloaded + where" | same person | 2026-11-06 | Evidence for this checklist |
| Record the exact file names and any content requirements in this file | whoever downloads | same day | Replaces the "UNKNOWN" cells above |

> Do **not** paste copyrighted course documents into a public repository. Keep them in the private
> team space or reference them by link.

## 3. What the course news already fixes (safe to rely on)

- Sprint boundaries and presentation dates (see [DSD_COURSE_CALENDAR.md](DSD_COURSE_CALENDAR.md)).
- Presentation uploads are due **Monday 23:59** before the presentation.
- Project Plan v1 is **versioned presentation slides**, not a Markdown document.
- Requirements Definition v1 and Design Description v1 are due **2026-11-13**; the design description may
  be a living document or maintained in a suitable tool.
- Product Backlog, Sprint Backlog and Sprint Burndown must be **living and always accessible to
  supervisors**.
- Sprint Review **and** Sprint Retrospective reports are **static presentation slides after each sprint**,
  including sprints without an oral presentation.
- Acceptance Test Plan (2026-12-25) and Acceptance Test Report (2027-01-04) are **static presentation
  slides**.
- Installation/deployment documentation, Final Report (**max 20 pages**) and the final product are due
  **2027-01-17**.
- Sprints 2+ must have an MVP/prototype **ready to test** at sprint end.

## 4. Provisional assumptions we are making (must be confirmed)

| # | Assumption | Risk if wrong | Where it is visible |
|---|---|---|---|
| A-01 | Sprint Review and Sprint Retrospective may be delivered as two separate decks (we produce separate ones, which is the safer superset) | Minor rework / merge | `presentations/sprint-01-review.pptx`, `presentations/sprint-01-retrospective.pptx` |
| A-02 | A 16:9 deck with title/agenda/context/demo/results/next-steps is acceptable | Deck rework before 2026-11-09 | `presentations/README.md` |
| A-03 | Documents in Markdown (versioned in Git) are acceptable where the course does not mandate a format | Rework to DOCX/PDF | `docs/REQUIREMENTS.md`, `docs/DESIGN_DESCRIPTION.md` |
| A-04 | The 20-page Final Report limit counts body pages; appendices/references may be extra | Report trimming | `docs/course/DSD_DELIVERABLES_REGISTER.md` |
| A-05 | Supervisors can be given read access to the Git repository / a living-tool export | Failing the "always accessible" requirement | `docs/PRODUCT_BACKLOG.md` |

## 5. How to update this file

When someone actually reads a guideline file, replace the row's status with **INSPECTED**, add the date,
the reader's role (not a fabricated name), and a short verbatim-safe summary of the concrete requirements.
Then re-check the decks and documents against it and record the outcome in
[../IMPLEMENTATION_LOG.md](../IMPLEMENTATION_LOG.md).
