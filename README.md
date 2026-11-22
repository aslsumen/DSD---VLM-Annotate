# VLM Annotate

**Human-verified temporal action datasets from long videos.**

A reviewer creates a project, describes an action in natural language, uploads a 10–30 minute single-view RGB
video, and starts an asynchronous VLM job. The system proposes timestamped candidate clips; a human marks each
one **true positive** or **false positive** — or leaves it **unreviewed**. The export is a ZIP with labels,
playable clips and auditable provenance.

> **AI proposes. Humans decide.** The product never invents a label, and an unreviewed candidate can never
> silently become a negative.

**Course:** Distributed Software Development (DSD) 2026/2027 · **Customer:** Gordan Kreković / Visage
Technologies · **Status:** Sprint 2 vertical slice (2026-11-05) — see [Status](#status).

---

## Quick start (Windows, verified)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
Copy-Item .env.example .env

cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000     # terminal 1
..\.venv\Scripts\python.exe -m app.worker --loop                   # terminal 2

cd ..\frontend
npm ci
npm run build          # then reload http://127.0.0.1:8000
# or: npm run dev      # http://127.0.0.1:5173 with API proxy
```

- App: <http://127.0.0.1:8000> · API docs: <http://127.0.0.1:8000/api/docs>
- Health: <http://127.0.0.1:8000/api/v1/health>
- Detailed setup, configuration and troubleshooting: [docs/INSTALLATION_MANUAL.md](docs/INSTALLATION_MANUAL.md)

## Verify the build

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q                 # 80 tests
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
.\.venv\Scripts\python.exe scripts\smoke_e2e.py                 # real ffmpeg, 26/26 checks
cd frontend; npm run build; npm test
```

## What works today

| Capability | State |
|---|---|
| Projects, action definitions, natural-language prompts | Working, tested |
| Video upload with limits, signature validation, ffmpeg probe | Working, tested |
| Range streaming for source video and clips | Working, tested |
| Asynchronous jobs: queue, worker, progress, retries, cancel, idempotency | Working, tested |
| Candidate intervals with proposal/preview separation | Working, tested |
| True/false-positive review, corrections, explicit unreviewed | Working (API), UI in progress |
| Dataset export: manifest, labels.csv, clips, provenance | Working, tested |
| Responsive web UI | Working — build + 21 unit tests + a headless-Chrome end-to-end pass (reported, not committed as a test) |
| **Real VLM inference** | **Integrated, not yet validated on product footage** — `videojev` adapter (VideoJev-4B, worker GPU); mock stays the default |
| 10–30 minute real footage validation | Not yet; real-model smoke on the 8 GB laptop pending (2026-11-16) |

## Repository map

```text
backend/
  app/                 FastAPI app, models, services, adapters, worker
    api/               REST routers (projects, videos, jobs, candidates, exports)
    services/          storage, media (ffmpeg), pipeline (queue/export)
    adapters/          VLMAdapter boundary: mock, videojev (real), Qwen2.5-VL (stub)
  alembic/             database migrations (initial schema verified)
  tests/               80 pytest tests
frontend/              React + TypeScript + Vite UI
video_grounding/       zero-shot grounding engine (VideoJev-4B), see video_grounding/README.md
presentations/         versioned decks (PPTX + editable Markdown source)
  content/             deck content as Python data
  deckbuild.py         renders content -> Markdown + PPTX
docs/
  course/              calendar, deliverables register, guidelines checklist
  decisions/           ADRs 0001–0007
  weekly-reports/      week-by-week factual reports
  sprint-reviews/      review + retrospective sources
  evidence/            real smoke-test JSON evidence
  *.md                 requirements, design, architecture, API, schema,
                       model evaluation, test plan, manuals, risks, backlogs
scripts/               smoke_e2e.py, smoke_videojev.py (real model, GPU host), render_burndown.py
```

## Design in one minute

- **API enqueues, worker executes.** `POST /videos/{id}/jobs` writes a row and returns `202`; a separate
  process claims it with an atomic conditional update. Inference never blocks a request.
- **Time is explicit.** All intervals are seconds relative to the source video, half-open `[start, end)`;
  proposal, preview and human correction are stored separately.
- **Unreviewed is structural.** No `is_negative` column exists; a label is an annotation row created by a
  person.
- **The model is replaceable.** One `VLMAdapter` interface; the mock is the CI default, `videojev` is the
  first real adapter ([ADR-0007](docs/decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md)).
- **Provenance travels with the data.** Adapter name/version, mock flag, clamping flag and source checksum are
  in every export.

Read more: [Architecture](docs/ARCHITECTURE.md) · [Design Description](docs/DESIGN_DESCRIPTION.md) ·
[API contracts](docs/API_CONTRACTS.md) · [Database schema](docs/DATABASE_SCHEMA.md) ·
[Model evaluation](docs/MODEL_EVALUATION.md) · [Dataset format](docs/DATASET_FORMAT.md).

## Status

Sprint 2 closed on **2026-11-15**. The increment is a runnable, tested **technical prototype** with mock
candidates — accounts, global roles, datasets, searches and OpenLABEL JSON are the Sprint 3 scope. The
real detector is the opt-in `videojev` adapter (VideoJev-4B; held-out long videos: cooking recall 0.86 (CI 0.81–0.90) and CCR 0.78, driving recall 0.47 and CCR 0.82, against targets of 0.85 for both, so not met;
see [MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md)).

Course artifacts are tracked in [docs/course/DSD_DELIVERABLES_REGISTER.md](docs/course/DSD_DELIVERABLES_REGISTER.md).
Known gap: the official `Guidelines (SCRUM, Presentations)` files are behind a FER login wall, so decks are
provisional ([checklist](docs/course/OFFICIAL_GUIDELINES_CHECKLIST.md)).

## Documentation index

| Need | Document |
|---|---|
| Install / configure / troubleshoot | [INSTALLATION_MANUAL.md](docs/INSTALLATION_MANUAL.md) |
| Use the product | [USER_MANUAL.md](docs/USER_MANUAL.md) |
| Requirements (28 FR, 14 NFR) | [REQUIREMENTS.md](docs/REQUIREMENTS.md) |
| Tests and actual results | [TEST_PLAN.md](docs/TEST_PLAN.md) |
| Risks | [RISK_REGISTER.md](docs/RISK_REGISTER.md) |
| Backlog / sprint plan / burndown | [PRODUCT_BACKLOG.md](docs/PRODUCT_BACKLOG.md), [SPRINT_BACKLOG.md](docs/SPRINT_BACKLOG.md), [SPRINT_BURNDOWN.md](docs/SPRINT_BURNDOWN.md) |
| **Customer decisions (latest emails)** | [CUSTOMER_DECISIONS.md](docs/customer/CUSTOMER_DECISIONS.md) |
| **Client meeting brief (13 Nov 2026)** | [CLIENT_MEETING_BRIEF_2026-11-13.md](docs/CLIENT_MEETING_BRIEF_2026-11-13.md) · [DOCX](docs/CLIENT_MEETING_BRIEF_2026-11-13.docx) · [PDF](docs/CLIENT_MEETING_BRIEF_2026-11-13.pdf) |
| **As-built prototype baseline (2026-11-05)** | [IMPLEMENTED_BASELINE_2026-11-05.md](docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md) |
| Weekly reports | [week-01](docs/weekly-reports/week-01.md), [week-02](docs/weekly-reports/week-02.md) |
| Decisions | [docs/decisions/](docs/decisions/) |
| Decks and upload checklist | [presentations/README.md](presentations/README.md) |

## Data and privacy

Never commit footage, credentials or `.env`. Uploads live under `data/storage/` (git-ignored) behind generated
keys; deleting a project or video removes its media. Model weights are not committed.

## Licence

Course project; source is for the DSD team and supervisors. Model licences differ per checkpoint — see
[MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md) §3 before distributing any weights.
