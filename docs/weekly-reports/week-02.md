# Week 02 Report — 2026-11-02 → 2026-11-08

**Sprint:** 2 (2026-11-02 → 2026-11-15) · **Written:** 2026-11-05 (mid-week) · **Author:** implementation
harness · **Team capacity:** not provided

> This is a mid-week report: the week is not over. Anything not yet executed is marked `NOT RUN` / `TODO`
> rather than assumed. The next update is due after the 2026-11-10 presentation.

## 1. Goal for the week

Deliver the vision presentation (Nov 3, missed from Sprint 1), establish a testable requirements/design
baseline, prepare the **Requirements & Design** deck for upload by **2026-11-09 23:59**, and keep Sprint 2 on
track for a testable MVP on **2026-11-15**.

## 2. Work completed (2026-11-05)

### Code

| Area | Delivered |
|---|---|
| Backend | FastAPI app, 7-table schema, Alembic migration, error envelope, optional bearer auth |
| Media | Streamed upload (signature/size/duration checks), ffmpeg probe, range streaming, H.264/AAC clip extraction |
| Async | DB queue, atomic claim, separate worker (`--once/--loop/--drain`), retry/backoff, manual retry, cancel, idempotency |
| Candidates | Clamping, proposal/preview split, per-candidate clip status, review filters |
| Review | TP/FP upsert, corrected boundaries, delete-to-unreviewed, notes/reviewer |
| Export | Async ZIP with manifest schema 1.0, labels.csv, README, clips, provenance |
| Frontend | Responsive React/TypeScript UI (projects, workspace, review, exports) — see §4 |

### Tests and checks (actual)

| Check | Command | Result |
|---|---|---|
| Unit + API tests | `.\.venv\Scripts\python.exe -m pytest -q` | **56 passed**, 1 dependency deprecation warning |
| Lint | `ruff check app tests` | **passed** |
| Format | `ruff format --check` | **passed** after formatting |
| Migration | `alembic upgrade head` on fresh SQLite | **passed** — 7 tables match metadata |
| Real ffmpeg E2E | `scripts\smoke_e2e.py` | **26/26 checks passed** |
| Frontend build | `npm run build` | see §4 |

### Documents

Course calendar, deliverables register, guidelines checklist, requirements (28 FR / 14 NFR), design
description, architecture, API contracts, database schema, model evaluation, test plan, risk register, product
backlog, sprint backlog, burndown (+SVG), working agreements, installation/user manuals, dataset format, demo
runbook, ADRs 0001–0006, weekly reports, Sprint 1 review/retrospective, implementation log, release notes.

### Presentations

- `01-project-vision-plan-v1.pptx` (16 slides) — **late**, upload pending.
- `02-requirements-design-v1.pptx` (20 slides) — ready for the 2026-11-09 upload.
- `sprint-01-review.pptx`, `sprint-01-retrospective.pptx` — late, upload pending.

## 3. What is not done yet

| Item | Status | Owner | By |
|---|---|---|---|
| Course-page uploads (Project Plan v1, Requirements & Design) | **TODO — manual** | Scrum Master | 11-06 / 11-09 |
| Download official guideline files (401 wall) | **BLOCKED** | team member with AAI | 11-06 |
| Team names, capacity, time zones | **TODO** | Scrum Master | 11-06 |
| Supervisor access to living artifacts | **TODO** | Product Owner | 11-07 |
| Real 10–30 min video validation | **TODO** | QA | 11-13 |
| Requirement/design freeze | **TODO** | owners | 11-12 |
| Sprint 2 review/retro + MVP gate evidence | **TODO** | Scrum Master | 11-15 |

## 4. UI workstream results

React 19 + TypeScript + Vite 7, no UI framework, hand-rolled hash router, mobile-first CSS.

| Check | Command | Result |
|---|---|---|
| Type-check + production build | `npm run build` (`tsc --noEmit && vite build`) | **PASS** — 0 TS errors, 41 modules; `dist/index.html` 0.89 kB, CSS 18.34 kB (gzip 4.44), JS 285.93 kB (gzip 86.49); 1.48 s |
| Unit tests | `npm test` (`vitest run`) | **PASS — 21 tests** in 2 files (`format` 13, `router` 8) |
| SPA served by API | `TestClient` + live `uvicorn` on :8010 | **PASS** — `GET /` 200 `text/html` with `#root`; `/api/v1/health` ok; `/api/docs` 200 |
| Browser end-to-end | headless Chrome against built app + real API/worker | **PASS (reported by the UI workstream; screenshots not retained)** — 12 s MP4 uploaded through the file input (`00:00:12`, 640×360, 25 fps), mock job polled to `succeeded`, 4 candidates, `J` saved TP, auto-advance to rank 2, invalid correction rejected client-side, valid correction + note saved, reset worked, clip played (`readyState 4`), filters/arrows worked, project create/delete, export `ready` (1 item), 375 px layouts with no page overflow (`scrollWidth = 375`), no console errors |
| Not exercised in browser | — | retry/cancel buttons, `NO_REVIEWED_CANDIDATES`, ZIP download click, UI project PATCH, token-protected deployment |

Implemented screens: projects list/create/delete with stats; project workspace (actions, upload with
progress, videos, jobs with polling + retry/cancel, exports); review screen (source player, clip player,
J/F shortcuts, filters, unreviewed counter, corrected boundaries, notes/reviewer, auto-advance, MOCK banner);
404 route. Accessibility: labelled controls, focus styles, `aria-live` status regions.

**Known limitation (R-18):** browsers cannot attach an `Authorization` header to `<video src>`, so a
token-protected deployment (`VLM_API_TOKEN` set) returns 401 on stream/clip and playback breaks. Development
runs token-off. Media auth (signed URLs or cookies) is backlog item PB-41.

## 5. Decisions this week

| Decision | ADR |
|---|---|
| Database-backed job queue instead of Celery/Redis | ADR-0001 |
| Source-relative half-open seconds; three interval families | ADR-0002 |
| Unreviewed = absence of an annotation row | ADR-0003 |
| Mock for Sprint 2; Qwen2.5-VL windowed for Alpha; SmolVLM2 fallback | ADR-0004 |
| Local storage behind a `StorageBackend` protocol | ADR-0005 |
| Optional shared bearer token, enforced in middleware | ADR-0006 |

## 6. Risks updated

R-03 (real inference) remains the biggest product risk; R-01 (guidelines) and R-12 (supervisor access) are the
biggest course-compliance risks. R-05 (late deck) is recorded as occurred. Full register:
[RISK_REGISTER.md](../RISK_REGISTER.md).

## 7. Files created or changed

```text
README.md, .gitignore, .env.example
backend/ (app/, alembic/, tests/, pyproject.toml, requirements*.txt)
frontend/ (Vite + React + TS app, tests, README)
presentations/ (4 PPTX, 4 Markdown sources, deckbuild.py, content/, README)
scripts/smoke_e2e.py, scripts/render_burndown.py
docs/course/*, docs/decisions/*, docs/weekly-reports/*, docs/sprint-reviews/*,
docs/retrospectives/*, docs/evidence/*, docs/burndown/*, docs/meeting-minutes/README.md
docs/{PROJECT_PLAN,REQUIREMENTS,DESIGN_DESCRIPTION,ARCHITECTURE,API_CONTRACTS,DATABASE_SCHEMA,
      MODEL_EVALUATION,TEST_PLAN,RISK_REGISTER,PRODUCT_BACKLOG,SPRINT_BACKLOG,SPRINT_BURNDOWN,
      TEAM_WORKING_AGREEMENTS,IMPLEMENTATION_LOG,RELEASE_NOTES,INSTALLATION_MANUAL,USER_MANUAL,
      DATASET_FORMAT,DEMO_RUNBOOK}.md
```

No commit was created; the repository was only initialised (`git init`). Committing follows the team's policy.

## 8. Next week's dependencies

1. Guidelines downloaded → decks validated before 11-09 upload.
2. Presentation feedback (11-10) → backlog items and requirements adjustments.
3. Real footage available with consent → NFR-02 validation by 11-13.
4. Capacity data → workload rebalance on 11-11.
