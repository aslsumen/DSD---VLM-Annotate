# Installation Manual

**Status:** living document (2027-01-17 static deliverable will freeze this)
**Verified environment:** Windows 11 · Python 3.14.4 · Node 24.22 · ffmpeg bundled via `imageio-ffmpeg`
**Verified on:** 2026-11-16 with a clean `git clone` followed by the steps below (80 backend tests, 21 UI tests,
26/26 smoke checks, API and worker running). macOS/Linux use the same steps with `.venv/bin/python` instead of
`.venv\Scripts\python.exe`.
**GPU engine:** `video_grounding/` is optional, Linux/WSL2 only, and documented separately — it is **not**
needed to run the web app.

VLM Annotate has three parts: a FastAPI **API**, a background **worker**, and a React **web UI**. For the
course demo all three run on one machine.

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 – 3.14 (verified 3.14.4) | `python --version` (Windows) / `python3 --version` (macOS/Linux) |
| Node.js | **≥ 20.19** (22 LTS recommended; verified 24.22) | `node --version` — Vite 7 fails on older Node |
| npm | bundled with Node | `npm --version` |
| Disk | ≥ 5 GB free | videos, clips and exports |
| OS | Windows 10/11 verified end-to-end; macOS/Linux expected (same commands, `.venv/bin/python`) | macOS/Linux not yet verified on a clean machine |
| NVIDIA GPU | optional | only for `video_grounding/` (Linux/WSL2); the app runs without it |

ffmpeg does **not** need a system install: the `imageio-ffmpeg` wheel ships a binary. Set
`VLM_FFMPEG_BINARY` only if you want to use a different build.

## 2. Get the code

```powershell
git clone https://github.com/aslsumen/DSD---VLM-Annotate.git
cd DSD---VLM-Annotate
```

Use `main`. The old `backend` branch was merged through PR #42; do not develop on it.

### 2.1 Fast path (recommended)

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

```bash
# macOS / Linux
bash scripts/setup.sh
```

The script checks Python/Node versions, creates `.venv`, installs the backend lockfile, applies migrations and
builds the UI. Then start the API and worker in two terminals (sections 3 and 4).

## 3. Backend and worker

Windows commands below; on macOS/Linux replace `.\.venv\Scripts\python.exe` with `.venv/bin/python` and use
forward slashes (the setup scripts handle this automatically).

```powershell
# 1. virtual environment at the repository root
python -m venv .venv

# 2. pinned dependencies
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt

# 3. configuration (optional; defaults work locally)
Copy-Item .env.example .env

# 4. database schema
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
```

> **Run the migration before starting the API for the first time.** The API defaults to
> `VLM_AUTO_CREATE_SCHEMA=true`; if it starts on an empty database it creates the tables *without* Alembic's
> version row, and any later `alembic upgrade head` fails with `table ... already exists`. Recovery: stop the
> API/worker, delete the development database (`data/vlm_annotate.db`, no real data), rerun the migration, and
> start the API again.
>
> **Keep `VLM_API_TOKEN` unset for demos**: browsers cannot send the bearer header to `<video>`, so playback
> returns 401 when the token is enabled (known limitation R-18).

Start the API (terminal 1):

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the worker (terminal 2):

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.worker --loop
```

Useful worker modes: `--once` (process at most one job), `--drain` (process the queue then exit).

Check it:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

## 4. Web UI

**Development (hot reload, port 5173):**

```powershell
cd frontend
npm ci
npm run dev
# open http://127.0.0.1:5173  (Vite proxies /api to :8000)
```

**Production build served by the API:**

```powershell
cd frontend
npm ci
npm run build          # emits frontend/dist
cd ..
# restart uvicorn: it mounts frontend/dist at /
# open http://127.0.0.1:8000
```

The API serves the SPA at `/` and the REST API at `/api/v1`; interactive docs are at `/api/docs`.

## 5. Configuration

Environment variables (prefix `VLM_`) or a `.env` file at the repository root:

| Variable | Default | Purpose |
|---|---|---|
| `VLM_DATABASE_URL` | `sqlite:///data/vlm_annotate.db` | SQLAlchemy URL; PostgreSQL supported |
| `VLM_DATA_DIR` | `./data` | Root for `storage/videos`, `storage/clips`, `storage/exports` |
| `VLM_API_TOKEN` | *(empty)* | When set, all `/api/v1` routes require `Authorization: Bearer <token>`. **Known limitation:** browsers cannot send this header for `<video>` playback, so stream/clip requests will 401 — do not enable it for demos that need video until PB-41 (signed media URLs) lands |
| `VLM_AUTH_REQUIRED` | `false` | Session auth for the `/api/v1/auth` and `/api/v1/datasets` routes. Set `true` to reject anonymous calls there |
| `VLM_BOOTSTRAP_TOKEN` | *(empty)* | One-time secret for `POST /api/v1/auth/bootstrap`, which creates the first administrator. Disabled when empty |
| `VLM_AUTH_SESSION_HOURS` | `12` | Absolute session lifetime |
| `VLM_AUTH_INVITATION_HOURS` | `48` | Invitation lifetime (single use) |
| `VLM_AUTH_MAX_FAILED_LOGINS` | `5` | Failures before the account is locked |
| `VLM_AUTH_LOCKOUT_MINUTES` | `15` | Lockout duration |
| `VLM_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Upload cap |
| `VLM_MAX_VIDEO_DURATION_SECONDS` | `14400` (4 h) | Hard duration cap |
| `VLM_VLM_ADAPTER` | `mock` | Default adapter: `mock` or `videojev` (see 5.1) |
| `VLM_VIDEOJEV_CONFIG` | *(empty)* | Path to a `video_grounding` YAML settings file; empty = engine defaults |
| `VLM_CLIP_PADDING_SECONDS` | `1.0` | Preview padding around a candidate |
| `VLM_CLIP_MAX_DURATION_SECONDS` | `90` | Maximum preview clip length |
| `VLM_MAX_CANDIDATES_PER_JOB` | `12` | Candidate cap |
| `VLM_WORKER_MAX_ATTEMPTS` | `3` | Retry budget |
| `VLM_WORKER_RETRY_BACKOFF_SECONDS` | `5` | Linear backoff base |
| `VLM_WORKER_HEARTBEAT_SECONDS` | `30` | Worker heartbeat interval; a running job is reclaimed after 3 missed beats. Only changes how fast a crashed job is retried |
| `VLM_CORS_ORIGINS` | localhost:5173/4173 | JSON list for the dev frontend |
| `VLM_FFMPEG_BINARY` | *(auto)* | Override the ffmpeg executable |
| `VLM_AUTO_CREATE_SCHEMA` | `true` | Dev convenience; use Alembic in production |

> Never commit `.env`. It is git-ignored.

### 5.1 Real inference with the `videojev` adapter (worker only)

**Platform:** the engine runs on **Linux or WSL2** with an NVIDIA GPU and CUDA. It is not supported natively on
Windows: run it inside WSL2. The web app does not need it.

The API process needs nothing extra. The **worker** venv must have the engine (Python 3.12, CUDA torch installed
first, see `video_grounding/docs/COMPATIBILITY.md`):

```bash
pip install -e ./video_grounding[videojev]
VLM_VLM_ADAPTER=videojev VLM_VIDEOJEV_CONFIG=video_grounding/configs/<file>.yaml python -m app.worker --loop
```

The API process only checks that `VLM_VIDEOJEV_CONFIG` (if set) exists, so it can enqueue `videojev` jobs
without the engine. A worker without the engine fails such a job at once with `ADAPTER_UNAVAILABLE`.
Engine state per job is kept in
`data/storage/engine/job-<id>/` and reused on retry; delete a job's directory to force a rescan. The adapter
always turns off Gemini verification and engine clip cutting, whatever the YAML says.

The adapter also caches each video's visual features under `data/storage/engine/features/video-<id>/`, so later
searches on the same video run faster. Size the data volume for the cap (`feature_cache.max_gb`, default 50 GB;
about 5 GB per hour of searched video, least recently used entries are evicted). To disable or shrink it, set
`feature_cache: {dir: null}` or a smaller `max_gb` in the YAML named by `VLM_VIDEOJEV_CONFIG`. Details:
[ARCHITECTURE.md](ARCHITECTURE.md#visual-feature-cache).

To check a GPU host end to end with the real model (API and worker running, several minutes per video):

```bash
python scripts/smoke_videojev.py --base-url http://127.0.0.1:8000 --action "person opens a door" a.mp4 b.mp4
```

## 6. Verify the installation

```powershell
# automated checks
.\.venv\Scripts\python.exe -m pytest backend -q            # expect 80 passed
.\.venv\Scripts\python.exe scripts\smoke_e2e.py            # expect 26/26 checks

# ffmpeg diagnostics
Invoke-RestMethod http://127.0.0.1:8000/api/v1/system/media
```

Then, in the browser: create a project, add an action, upload a short mp4, start processing, wait for
candidates, label one, export, download the ZIP.

## 7. Database operations

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic downgrade -1
```

**Backup:** stop the worker and the API, then copy the whole `data/` directory (database + media). A database
without `data/storage/` has no videos or clips. Restore by copying it back before starting the services.

**Reset (destroys all data):** stop services and delete `data/`.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `422 MEDIA_PROBE_FAILED` on upload | File is not decodable / truncated | Re-export the video; check `GET /api/v1/system/media` |
| `415 UNRECOGNISED_CONTAINER` | Wrong extension or non-video bytes | Use mp4/mov/m4v/webm/mkv; do not rename a file's extension |
| `413 UPLOAD_TOO_LARGE` | Above `VLM_MAX_UPLOAD_BYTES` | Raise the limit or compress the video |
| Job stays `queued` | Worker not running | Start `python -m app.worker --loop` |
| Job `running` but nothing happens | Worker died mid-job | Restart the worker: after 3 missed heartbeats (`VLM_WORKER_HEARTBEAT_SECONDS`) the job is requeued with `WORKER_LOST`; or cancel it in the UI |
| Job `failed` with `FFMPEG_NOT_FOUND` | No ffmpeg binary | `pip install imageio-ffmpeg` or set `VLM_FFMPEG_BINARY` |
| `401 UNAUTHENTICATED` in UI | `VLM_API_TOKEN` set but no token entered | Paste the token in the UI / send the header |
| `CORS` error in dev | Frontend port not allowed | Add it to `VLM_CORS_ORIGINS` |
| Port 8000 busy | Another process | `--port 8001` and update the Vite proxy |
| Clips missing, candidates present | ffmpeg failure on that file | Check job `error_code=CLIP_EXTRACTION_PARTIAL`; source video still reviewable |
| `ModuleNotFoundError: app` | Wrong working directory | Run commands from `backend/` |
| `table projects already exists` during migration | API started before migrations | Stop API/worker, delete `data/vlm_annotate.db` (dev), rerun `alembic upgrade head` |
| `npm ci` or Vite fails with an engine/version error | Node older than 20.19 | Install Node 22 LTS and delete `frontend/node_modules` |
| Engine install fails on Windows | GPU engine is Linux/WSL2 only | Use WSL2; the app works without the engine |
| `python` not found (macOS/Linux) | Only `python3` is installed | Use `python3` or set `PYTHON=python3` for the setup script |
| `.venv/bin/python` not found (Windows) | Unix path used on Windows | Use `.venv\Scripts\python.exe` |

## 9. Optional: PostgreSQL

```powershell
.\.venv\Scripts\python.exe -m pip install "psycopg[binary]"
$env:VLM_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/vlm_annotate"
cd backend; ..\.venv\Scripts\python.exe -m alembic upgrade head
```

This path is **not yet verified** in this project (`R-09`).

## 10. Uninstall

Stop the processes, delete the virtual environment, `frontend/node_modules`, `frontend/dist` and the `data/`
directory. Nothing is installed system-wide.
