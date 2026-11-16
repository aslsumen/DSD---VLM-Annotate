# Sprint Backlog — Sprint 2 (2026-11-02 → 2026-11-15)

**Type:** living artifact · **Owner:** Scrum Master (role placeholder) · **Last updated:** 2026-11-05
**Sprint goal:** *By 2026-11-15, a reviewer can create a project, upload a long video, run an asynchronous
job, review timestamped candidate clips as true/false positives, and download a provenance-complete dataset —
with the Requirements & Design presentation delivered on 2026-11-10 and Requirements/Design v1 documents
frozen on 2026-11-13.*

**Capacity:** **UNKNOWN.** No team member has entered availability. The table below therefore uses task
estimates only. It must be replaced with per-person capacity (target 80–85 % of declared availability) before
the mid-sprint review on 2026-11-11. Public holiday inside the sprint: none (2026-11-18 falls in Sprint 3).

> **Scope update (2026-11-12).** The customer's latest answers and the team's v1.1 documents add accounts,
> global roles, datasets, searches and OpenLABEL JSON to the MVP. The Sprint 2 increment is therefore a
> **technical, testable prototype**, not the full v1.1 MVP. See
> [CLIENT_MEETING_BRIEF_2026-11-13.md](CLIENT_MEETING_BRIEF_2026-11-13.md) §4 and risks R-19/R-22.

## 1. Tasks

| ID | Task | Refs | Est. (SP) | Owner (role) | Status | Evidence |
|---|---|---|---|---|---|---|
| S2-01 | Course calendar, deliverables register, guidelines checklist | D-01…D-16 | 3 | Scrum Master | **Done 11-05** | `docs/course/*` |
| S2-02 | Project Plan v1 deck (late) + PPTX | D-01 | 5 | Product Owner | **Done 11-05 (not uploaded)** | `presentations/01-*` |
| S2-03 | Sprint 1 review + retrospective decks | D-07, D-08 | 3 | Scrum Master | **Done 11-05 (late)** | `presentations/sprint-01-*` |
| S2-04 | Repository bootstrap, lint/test baseline, migrations | — | 3 | Backend | **Done 11-05** | `.venv`, `alembic/`, 56 tests |
| S2-05 | Projects/actions/videos API + upload validation + probe | PB-01…PB-08 | 8 | Backend | **Done 11-05** | `backend/app/api/*`, tests |
| S2-06 | Async job queue, worker, retries, progress | PB-09…PB-14 | 8 | Backend | **Done 11-05** | `services/pipeline.py`, `worker.py` |
| S2-07 | Candidates with proposal/preview split + real clips | PB-15, PB-16 | 5 | Backend/ML | **Done 11-05** | smoke evidence 26/26 |
| S2-08 | Annotation API: TP/FP, corrections, unreviewed state | PB-17…PB-19 | 5 | Backend | **Done 11-05** | `api/candidates.py` |
| S2-09 | Async export ZIP with manifest + provenance | PB-21…PB-23 | 5 | Backend | **Done 11-05** | `services/pipeline.py` |
| S2-10 | Automated tests + real ffmpeg smoke script | NFR-11 | 5 | QA | **Done 11-05** | `pytest` 56 passed, `docs/evidence/*` |
| S2-11 | Requirements Definition + Design Description drafts | D-02, D-03 | 5 | Requirements/Architect | **Done 11-05 (draft)** | `docs/REQUIREMENTS.md`, `docs/DESIGN_DESCRIPTION.md` |
| S2-12 | Model evaluation + adapter boundary + mock | PB-24 prereq | 3 | ML | **Done 11-05** | `docs/MODEL_EVALUATION.md`, `adapters/` |
| S2-13 | Responsive UI: projects, workspace, review, export | PB-20 | 8 | Frontend | **Done 11-05** | `frontend/` — build + 21 tests + headless-Chrome E2E |
| S2-14 | Requirements & Design deck source + PPTX | D-15 | 5 | Architect | **Done 11-05** | `presentations/02-*` (20 slides) |
| S2-15 | Installation + user manuals | PB-35 | 3 | DevOps | **Done 11-05** | `docs/INSTALLATION_MANUAL.md`, `USER_MANUAL.md` |
| S2-16 | Team capacity, supervisor access, guideline download | R-01, R-12 | 2 | Scrum Master | **Blocked (human)** | — |
| S2-17 | Validate on a real 10–30 min video (not only synthetic) | NFR-02 | 3 | QA | **Carried to Sprint 3** | — |
| S2-18 | Sprint 2 review/retro + MVP gate evidence | D-09 | 3 | Scrum Master | **Done 11-15** | `presentations/sprint-02-*.pptx` |

**Total:** 82 SP · **Done:** 77 SP · **Blocked (human):** 2 SP · **Carried over:** 3 SP.

**Sprint 2 closed 2026-11-15.** Verdict: the increment is a **testable technical prototype** (mock detector),
not the v1.1 MVP. The scope expanded on 9 Nov (accounts, roles, datasets, searches, JSON) and that work moves
to Sprint 3. No story point is claimed without an artifact in the repository.

## 2. Daily plan for the remainder of the sprint

The first three days of Sprint 2 (Nov 2–4) have **no repository evidence**: the repository was created and
the work below was executed on 2026-11-05. This is stated so the burndown is not mistaken for team velocity.

| Date | Day | Planned work | Owner | Gate |
|---|---|---|---|---|
| 11-05 | Thu | Backend slice, tests, docs, S1 decks, course artifacts (done) | Harness/Backend | tests green |
| 11-06 | Fri | Finish UI; download official guidelines; team names + capacity; upload late Project Plan v1 | Frontend, Scrum Master | UI builds; guidelines checklist updated |
| 11-07 | Sat | **No work assumed** (weekend) | — | — |
| 11-08 | Sun | **No work assumed** (weekend) | — | — |
| 11-09 | Mon | Freeze Requirements & Design deck; **upload by 23:59**; supervisor access for Scrum artifacts | Architect, PO | upload evidence recorded |
| 11-10 | Tue | Deliver Requirements & Design presentation; capture real feedback | All | feedback in minutes |
| 11-11 | Wed | Mid-sprint load review; fix deck feedback; start real 10–30 min video validation | Scrum Master, QA | capacity table filled |
| 11-12 | Thu | Freeze Requirements v1 / Design v1; final fixes | Requirements, Architect | docs frozen |
| 11-13 | Fri | **Requirements v1 + Design v1 due 23:59**; real-video validation result recorded | Owners | deliverables submitted |
| 11-14 | Sat | Buffer / contingency only | — | — |
| 11-15 | Sun | **Sprint 2 ends:** MVP gate evidence, review + retrospective, burndown closed | Scrum Master | PASS/FAIL gate |

## 3. Blockers and dependencies

| Blocker | Blocks | Owner | Needed by |
|---|---|---|---|
| `Guidelines (SCRUM, Presentations)` behind FER login (HTTP 401) | Deck/document validation, A-01…A-05 | Team member with AAI | **11-06** |
| No real team names/capacity | Workload balance, burndown credibility | Scrum Master | **11-06** |
| Supervisor access to living artifacts not configured | Course requirement D-04…D-06 | Product Owner | **11-07** |
| No real VLM on the laptop (no torch/weights) | Alpha gate, not Sprint 2 gate | ML owner | Sprint 3 |
| No real 10–30 min footage tested yet | NFR-02 claim | QA | 11-13 |

## 4. Sprint 2 exit checklist (2026-11-15)

- [ ] UI builds and the whole flow works in a browser (desktop + 375 px)
- [ ] `pytest` green; `ruff check` clean; smoke script 26/26
- [ ] Requirements & Design deck uploaded and presented (evidence recorded)
- [ ] Requirements v1 and Design v1 frozen and submitted (2026-11-13)
- [ ] Real ≥10-minute video processed end-to-end with mock adapter; limitations documented
- [ ] Product Backlog, Sprint Backlog, burndown accessible to supervisors
- [ ] Sprint 2 review + retrospective slides produced with real results
- [ ] Risks updated; no fabricated measurements
