# Installation Manual

**Status:** draft for Sprint 2 (2027-01-17 static deliverable will freeze this)
**Verified environment:** Windows 11 · Python 3.14.4 · Node 24.22 · ffmpeg bundled via `imageio-ffmpeg`
**Verified on:** 2026-11-05 (see `docs/evidence/`)

VLM Annotate has three parts: a FastAPI **API**, a background **worker**, and a React **web UI**. For the
course demo all three run on one machine.

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 (verified 3.14.4) | `python --version` |
| Node.js | ≥ 20 (verified 24.22) | `node --version` |
| npm | bundled with Node | `npm --version` |
| Disk | ≥ 5 GB free | videos, clips and exports |
| OS | Windows 10/11 verified; macOS/Linux expected but **untested** | paths below use PowerShell |

ffmpeg does **not** need a system install: the `imageio-ffmpeg` wheel ships a binary. Set
`VLM_FFMPEG_BINARY` only if you want to use a different build.

## 2. Get the code

```powershell
git clone <repository-url> vlm-annotate
cd vlm-annotate
```

## 3. Backend and worker

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
| `VLM_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Upload cap |
| `VLM_MAX_VIDEO_DURATION_SECONDS` | `14400` (4 h) | Hard duration cap |
| `VLM_VLM_ADAPTER` | `mock` | Default adapter: `mock` or `videojev` (see 5.1) |
| `VLM_VIDEOJEV_CONFIG` | *(empty)* | Path to a `video_grounding` YAML settings file; empty = engine defaults |
| `VLM_CLIP_PADDING_SECONDS` | `1.0` | Preview padding around a candidate |
| `VLM_CLIP_MAX_DURATION_SECONDS` | `90` | Maximum preview clip length |
| `VLM_MAX_CANDIDATES_PER_JOB` | `12` | Candidate cap |
| `VLM_WORKER_MAX_ATTEMPTS` | `3` | Retry budget |
| `VLM_WORKER_RETRY_BACKOFF_SECONDS` | `5` | Linear backoff base |
| `VLM_CORS_ORIGINS` | localhost:5173/4173 | JSON list for the dev frontend |
| `VLM_FFMPEG_BINARY` | *(auto)* | Override the ffmpeg executable |
| `VLM_AUTO_CREATE_SCHEMA` | `true` | Dev convenience; use Alembic in production |

> Never commit `.env`. It is git-ignored.

### 5.1 Real inference with the `videojev` adapter (worker only)

The API process needs nothing extra. The **worker** venv must have the engine (Python 3.12, an NVIDIA GPU, CUDA
torch installed first, see `video_grounding/docs/COMPATIBILITY.md`):

```bash
pip install -e ./video_grounding[videojev]
VLM_VLM_ADAPTER=videojev VLM_VIDEOJEV_CONFIG=video_grounding/configs/<file>.yaml python -m app.worker --loop
```

The API process only checks that `VLM_VIDEOJEV_CONFIG` (if set) exists, so it can enqueue `videojev` jobs
without the engine. A worker without the engine fails such a job at once with `ADAPTER_UNAVAILABLE`.
Engine state per job is kept in
`data/storage/engine/job-<id>/` and reused on retry; delete a job's directory to force a rescan. Gemini
verification is off by default.

## 6. Verify the installation

```powershell
# automated checks
.\.venv\Scripts\python.exe -m pytest backend -q            # expect 56 passed
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
| Job `failed` with `FFMPEG_NOT_FOUND` | No ffmpeg binary | `pip install imageio-ffmpeg` or set `VLM_FFMPEG_BINARY` |
| `401 UNAUTHENTICATED` in UI | `VLM_API_TOKEN` set but no token entered | Paste the token in the UI / send the header |
| `CORS` error in dev | Frontend port not allowed | Add it to `VLM_CORS_ORIGINS` |
| Port 8000 busy | Another process | `--port 8001` and update the Vite proxy |
| Clips missing, candidates present | ffmpeg failure on that file | Check job `error_code=CLIP_EXTRACTION_PARTIAL`; source video still reviewable |
| `ModuleNotFoundError: app` | Wrong working directory | Run commands from `backend/` |

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
