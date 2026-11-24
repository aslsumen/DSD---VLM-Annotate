# VLM Annotate

**Human-verified temporal action datasets from long videos.**

A reviewer creates a project, describes an action in natural language, uploads a 10–30 minute single-view RGB
video, and starts an asynchronous VLM job. The system proposes timestamped candidate clips; a human marks each
one **true positive** or **false positive** — or leaves it **unreviewed**. The export is a ZIP with labels,
playable clips and auditable provenance.

> **AI proposes. Humans decide.** The product never invents a label, and an unreviewed candidate can never
> silently become a negative.

**Course:** Distributed Software Development (DSD) 2026/2027 · **Customer:** Gordan Kreković / Visage
Technologies · **Status:** Sprint 3 (November 2026) — mock adapter is the default, the `videojev` real adapter is
integrated; see [Status](#status).

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **3.12 – 3.14** | `python --version` (Windows) / `python3 --version` (macOS/Linux) |
| Node.js | **≥ 20.19** (22 LTS recommended) | `node --version` — Vite 7 fails on older Node |
| npm | bundled with Node | `npm --version` |
| git | any recent version | to clone the repository |
| NVIDIA GPU (optional) | CUDA-capable | **only** for the real `video_grounding` engine; the web app runs without it |

The web app (API + worker + UI) needs **no GPU**: the default adapter is `mock`. The real engine
(`video_grounding/`) is optional and currently documented for **Linux/WSL2**; see
[Run the GPU engine](#run-the-gpu-engine-optional).

## 1. Clone

```bash
git clone https://github.com/aslsumen/DSD---VLM-Annotate.git
cd DSD---VLM-Annotate
```

Work on `main`. The old `backend` branch was merged through PR #42; do not use it for new work.

## 2. Run the web app (no GPU)

**Fast path (Windows PowerShell or macOS/Linux):** a setup script installs everything, migrates the database and
builds the UI.

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

```bash
# macOS / Linux
bash scripts/setup.sh
```

Then start the two processes:

```powershell
# Windows — terminal 1: API
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Windows — terminal 2: worker
cd backend
..\.venv\Scripts\python.exe -m app.worker --loop
```

```bash
# macOS / Linux — terminal 1: API
cd backend
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# macOS / Linux — terminal 2: worker
cd backend
../.venv/bin/python -m app.worker --loop
```

Open <http://127.0.0.1:8000> (UI) and <http://127.0.0.1:8000/api/docs> (API). The setup script already built
`frontend/dist`; if you change the UI, rebuild it and restart the API (it mounts `dist/` at startup).

**Manual path** (if you prefer to see every step):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000      # terminal 1
..\.venv\Scripts\python.exe -m app.worker --loop                    # terminal 2
cd ..\frontend
npm ci
npm run build
```

> **Migration order matters.** Always run `alembic upgrade head` **before** starting the API for the first time.
> The API has `VLM_AUTO_CREATE_SCHEMA=true`, so starting it on an empty database creates the tables *without*
> Alembic's version row; a later migration then fails with `table ... already exists`. Fix: stop the API, delete
> the development database (`data/vlm_annotate.db`, it contains no real data), run `alembic upgrade head`, and
> start the API again.

> **Keep `VLM_API_TOKEN` unset for demos.** Browsers cannot send the bearer header to `<video>`, so enabling the
> token makes source-video and clip playback return 401 (known limitation R-18).

## 3. Run the GPU engine (optional)

`video_grounding/` is the real zero-shot detector (VideoJev-4B). It is **not** needed to run or demo the web
app, which defaults to the labelled `mock` adapter. The engine requires **Linux or WSL2**, an NVIDIA GPU with
CUDA, `uv`, and several GB of model weights; it is **not** supported by the Windows instructions above (do not
use `.venv/bin/...` paths on Windows).

Start here:

- [video_grounding/README.md](video_grounding/README.md) — pipeline, quick start
- [video_grounding/docs/COMPATIBILITY.md](video_grounding/docs/COMPATIBILITY.md) — verified CUDA/torch/driver matrix
- [video_grounding/docs/USAGE.md](video_grounding/docs/USAGE.md) — configuration, CLI, troubleshooting

The adapter is enabled only in the worker: `VLM_VLM_ADAPTER=videojev VLM_VIDEOJEV_CONFIG=video_grounding/configs/<file>.yaml`.
The API accepts such jobs without the engine; a worker without it fails the job with `ADAPTER_UNAVAILABLE`.

## Verify the build

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest backend -q                 # 121 tests
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
.\.venv\Scripts\python.exe scripts\smoke_e2e.py                 # real ffmpeg, 26/26 checks
cd frontend; npm run build; npm test
```

```bash
# macOS / Linux
./.venv/bin/python -m pytest backend -q
./.venv/bin/python -m ruff check backend/app backend/tests
./.venv/bin/python scripts/smoke_e2e.py
cd frontend && npm run build && npm test
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run from `backend/` (where `app/` lives) or use the venv interpreter explicitly |
| `no such table: projects` | Run `alembic upgrade head` before starting the API |
| `table projects already exists` during migration | The API created the schema first. Stop it, delete `data/vlm_annotate.db` (dev only), rerun `alembic upgrade head` |
| `401 UNAUTHENTICATED` / video will not play | `VLM_API_TOKEN` is set. Unset it for the demo, or use the API only (R-18) |
| `npm ci` / Vite error about Node | Node is older than 20.19; install Node 22 LTS |
| `pip install` stalls silently | Stale pip cache (often after a killed install): kill leftover `python.exe` processes. Solution: rerun with `--no-cache-dir` |
| `ffmpeg not found` | `pip install imageio-ffmpeg` (already in the lockfile) or set `VLM_FFMPEG_BINARY` |
| Job stays `queued` | The worker is not running: start `python -m app.worker --loop` from `backend/` |
| Port 8000 in use | Use `--port 8001` and update `frontend/vite.config.ts` proxy |
| Windows cannot install the engine | Expected: use WSL2/Linux + CUDA + `uv`; the web app does not need the engine |
| `database is locked` | Close extra API/worker processes or other DB tools |

Still stuck: include your **OS**, `python --version`, `node --version`, the exact command and the full error
traceback when you ask for help.

## What works today

| Capability | State |
|---|---|
| Projects, action definitions, natural-language prompts | Working, tested |
| Video upload with limits, signature validation, ffmpeg probe | Working, tested |
| Range streaming for source video and clips | Working, tested |
| Asynchronous jobs: queue, worker, progress, retries, cancel, idempotency | Working, tested |
| Candidate intervals with proposal/preview separation | Working, tested |
| True/false-positive review, corrections, explicit unreviewed | Working (API + UI), tested |
| Dataset export: manifest, labels.csv, clips, provenance | Working, tested |
| Responsive web UI | Working — build + 21 unit tests + a headless-Chrome end-to-end pass (reported, not committed as a test) |
| **Real VLM inference** | **Integrated, not yet validated on product footage** — `videojev` adapter (VideoJev-4B, worker GPU); mock stays the default |
| 10–30 minute real footage validation | Not yet; real-model smoke on the 8 GB laptop pending (2026-11-16) |

## Repository map

```text
backend/
  app/                 FastAPI app, models, services, adapters, worker
    api/               REST routers (auth, datasets, searches, projects, videos, jobs, candidates, exports)
    services/          storage, media (ffmpeg), pipeline (queue/export)
    adapters/          VLMAdapter boundary: mock, videojev (real), Qwen2.5-VL (stub)
  alembic/             database migrations (initial schema verified)
  tests/               121 pytest tests (incl. search fan-out / status / scoping / listing / idempotency,
                       job-lifecycle sync on cancel / reaper / retry / video delete)
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
scripts/               setup.ps1, setup.sh, smoke_e2e.py, smoke_videojev.py (GPU host), render_burndown.py
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

Sprint 3 is in progress (2026-11-16 → 2026-11-29; Alpha gate 29 Nov). `main` contains the tested vertical slice
(mock adapter is the default), the opt-in `videojev` adapter and the `video_grounding` engine (Linux/WSL2 only;
Charades-STA reference numbers only, held-out composite results pending — see
[MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md)). Accounts, global roles, datasets, searches and OpenLABEL JSON
are the remaining Sprint 3 scope.

Course artifacts are tracked in [docs/course/DSD_DELIVERABLES_REGISTER.md](docs/course/DSD_DELIVERABLES_REGISTER.md).
Known gap: the official `Guidelines (SCRUM, Presentations)` files are behind a FER login wall, so decks are
provisional ([checklist](docs/course/OFFICIAL_GUIDELINES_CHECKLIST.md)).

## Documentation index

| Need | Document |
|---|---|
| Install / configure / troubleshoot | [INSTALLATION_MANUAL.md](docs/INSTALLATION_MANUAL.md) |
| Use the product | [USER_MANUAL.md](docs/USER_MANUAL.md) |
| Requirements (27 FR, 14 NFR) | [REQUIREMENTS.md](docs/REQUIREMENTS.md) |
| Tests and actual results | [TEST_PLAN.md](docs/TEST_PLAN.md) |
| Risks | [RISK_REGISTER.md](docs/RISK_REGISTER.md) |
| Backlog / sprint plan / burndown | [PRODUCT_BACKLOG.md](docs/PRODUCT_BACKLOG.md), [SPRINT_BACKLOG.md](docs/SPRINT_BACKLOG.md), [SPRINT_BURNDOWN.md](docs/SPRINT_BURNDOWN.md) |
| **Customer decisions (latest emails)** | [CUSTOMER_DECISIONS.md](docs/customer/CUSTOMER_DECISIONS.md) |
| **Client meeting brief (13 Nov 2026)** | [CLIENT_MEETING_BRIEF_2026-11-13.md](docs/CLIENT_MEETING_BRIEF_2026-11-13.md) · [DOCX](docs/CLIENT_MEETING_BRIEF_2026-11-13.docx) · [PDF](docs/CLIENT_MEETING_BRIEF_2026-11-13.pdf) |
| **As-built prototype baseline (2026-11-05)** | [IMPLEMENTED_BASELINE_2026-11-05.md](docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md) |
| Weekly reports | [week-01](docs/weekly-reports/week-01.md), [week-02](docs/weekly-reports/week-02.md), [week-03](docs/weekly-reports/week-03.md) |
| Decisions | [docs/decisions/](docs/decisions/) |
| Decks and upload checklist | [presentations/README.md](presentations/README.md) |

## Data and privacy

Never commit footage, credentials or `.env`. Uploads live under `data/storage/` (git-ignored) behind generated
keys; deleting a project or video removes its media. Model weights are not committed.

## Licence

Course project; source is for the DSD team and supervisors. Model licences differ per checkpoint — see
[MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md) §3 before distributing any weights.
