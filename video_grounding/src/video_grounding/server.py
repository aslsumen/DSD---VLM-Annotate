"""HTTP service over the grounding engine. One worker thread owns the (single-GPU) model; handlers only read
files and sqlite. Every id is a directory under jobs_root; request.json is written first so work survives a restart."""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import threading
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import dataset, persistence as P
from .adapters.base import make_backend
from .evaluation import evaluate_review
from .models import Query
from .scheduler import _write_json, resume, run_scan
from .settings import Settings

log = logging.getLogger("video_grounding.server")
_ID = re.compile(r"[A-Za-z0-9_-]+")
_URL = ("http://", "https://")


class PromptIn(BaseModel):
    query_id: str
    text: str


class JobIn(BaseModel):
    video: str
    prompts: list[PromptIn] | None = None
    prompt: str | None = None


class ReviewIn(BaseModel):
    event_id: str
    accepted: bool
    start_sec: float | None = None
    end_sec: float | None = None


class ReviewsIn(BaseModel):
    reviews: list[ReviewIn]


class DatasetIn(BaseModel):
    name: str
    job_ids: list[str]
    include_rejected: bool = False


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".tmp")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)


def _bad(msg: str) -> HTTPException:
    return HTTPException(400, msg)


def create_app(settings: Settings, jobs_root, *, backend=None, media_root=None) -> FastAPI:
    backend = backend or make_backend(settings)
    jobs, dsets = Path(jobs_root) / "jobs", Path(jobs_root) / "datasets"
    media = Path(media_root).resolve() if media_root else None
    q: queue.Queue = queue.Queue()
    stop, lock, review_lock = threading.Event(), threading.Lock(), threading.Lock()
    active: dict[str, str] = {}  # id -> "queued" | "running"

    def enqueue(kind: str, id_: str) -> bool:
        with lock:
            if id_ in active:
                return False
            active[id_] = "queued"
        q.put((kind, id_))
        return True

    def run(kind: str, id_: str) -> None:
        if kind == "dataset":
            req = json.loads((dsets / id_ / "request.json").read_text())
            dataset.build_dataset([jobs / j for j in req["job_ids"]], dsets / id_, req["name"],
                                  req["include_rejected"])
            return
        d = jobs / id_
        if kind == "resume":
            resume(d, backend=backend, keep_loaded=True)
            return
        req = json.loads((d / "request.json").read_text())
        video = req["video"]
        if video.startswith(_URL):
            src = d / "source.mp4"
            if not src.exists():
                _download(video, src)
            video = str(src)
        (d / "job.sqlite").unlink(missing_ok=True)  # a scan task means no job row: drop a leftover from a crash in probe
        run_scan(video, [Query(**x) for x in req["queries"]], settings, d, backend=backend, job_id=id_,
                 keep_loaded=True)

    def worker() -> None:
        while True:
            task = q.get()
            if task is None or stop.is_set():  # queued tasks stay on disk (request.json) and resume at next start
                return
            kind, id_ = task
            active[id_] = "running"
            try:
                run(kind, id_)
            except Exception as e:  # noqa: BLE001  one bad task must not kill the worker
                log.exception("%s %s failed", kind, id_)
                (dsets if kind == "dataset" else jobs).joinpath(id_, "error.txt").write_text(f"{type(e).__name__}: {e}")
            finally:
                active.pop(id_, None)

    def db_state(d: Path) -> str | None:
        if not (d / "job.sqlite").exists():
            return None
        conn = P.connect(d / "job.sqlite")
        try:
            return P.get_job(conn)["state"]
        except LookupError:
            return None
        finally:
            conn.close()

    def recover() -> None:
        for d in sorted(jobs.glob("*/request.json")):
            d = d.parent
            if (d / "error.txt").exists():
                continue
            state = db_state(d)
            if state is None:
                enqueue("scan", d.name)
            elif state not in ("completed", "failed"):
                enqueue("resume", d.name)
        for d in sorted(dsets.glob("*/request.json")):
            d = d.parent
            if not (d / "dataset.json").exists() and not (d / "error.txt").exists():
                enqueue("dataset", d.name)

    @asynccontextmanager
    async def lifespan(app):
        jobs.mkdir(parents=True, exist_ok=True)
        dsets.mkdir(parents=True, exist_ok=True)
        recover()
        t = threading.Thread(target=worker, name="grounding-worker", daemon=True)
        t.start()
        yield
        stop.set()
        q.put(None)
        t.join()  # ponytail: waits for the task in flight (the model call cannot be interrupted)

    app = FastAPI(title="video-grounding", lifespan=lifespan)

    def _dir(root: Path, id_: str) -> Path:
        d = root / id_
        if not _ID.fullmatch(id_) or not (d / "request.json").exists():
            raise HTTPException(404, f"unknown id {id_}")
        return d

    def _status(job_id: str) -> dict:
        d = _dir(jobs, job_id)
        req = json.loads((d / "request.json").read_text())
        err = (d / "error.txt").read_text() if (d / "error.txt").exists() else None
        state, progress = "queued", {}
        if (d / "job.sqlite").exists():
            conn = P.connect(d / "job.sqlite")
            try:
                state, progress = P.get_job(conn)["state"], P.stats(conn)["window_counts"]
            except LookupError:
                state = "probing"
            finally:
                conn.close()
        elif active.get(job_id) == "running":
            state = "probing"  # downloading / probing, nothing in sqlite yet
        evs = d / "events.json"
        doc = json.loads(evs.read_text()) if evs.exists() else None
        return {"job_id": job_id, "state": "failed" if err else state, "video": req["video"],
                "queries": req["queries"], "progress": progress, "error": err,
                "scan_complete": doc["scan_complete"] if doc else None,
                "n_events": len(doc["events"]) if doc else None}

    def _completed(job_id: str) -> Path:
        d = _dir(jobs, job_id)
        if _status(job_id)["state"] != "completed":
            raise HTTPException(409, "job is not completed")
        return d

    def _clip(d: Path, name: str) -> FileResponse:
        p = d / "clips" / f"{name}.mp4"
        if not _ID.fullmatch(name) or not p.is_file():
            raise HTTPException(404, "clip not found")
        return FileResponse(p, media_type="video/mp4")

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "model_id": backend.model_id, "model_revision": backend.model_revision,
                "model_loaded": getattr(backend, "_model", None) is not None,  # videojev only
                "queue_length": q.qsize()}

    @app.post("/v1/jobs", status_code=202)
    def create_job(body: JobIn):
        if (body.prompts is None) == (body.prompt is None):
            raise _bad("give exactly one of prompts / prompt")
        queries = body.prompts if body.prompts is not None else [PromptIn(query_id="q1", text=body.prompt)]
        ids = [p.query_id for p in queries]
        if not queries or "" in ids or len(set(ids)) != len(ids) or any(not p.text.strip() for p in queries):
            raise _bad("prompts need unique non-empty query_id and non-empty text")
        if "://" in body.video:
            if not body.video.startswith(_URL):
                raise _bad("only http(s) URLs and local paths are supported")
        else:
            p = Path(body.video).resolve()
            if media is not None and not p.is_relative_to(media):
                raise _bad("video path is outside the media root")
            if not p.is_file():
                raise _bad("video path does not exist")
        job_id = "job_" + uuid.uuid4().hex[:12]
        (jobs / job_id).mkdir(parents=True)
        _write_json(jobs / job_id / "request.json",
                    {"video": body.video, "queries": [p.model_dump() for p in queries]})
        enqueue("scan", job_id)
        return {"job_id": job_id, "state": "queued"}

    @app.get("/v1/jobs")
    def list_jobs():
        dirs = sorted(jobs.glob("*/request.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [_status(p.parent.name) for p in dirs]

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str):
        return _status(job_id)

    @app.get("/v1/jobs/{job_id}/events")
    def get_events(job_id: str):
        return json.loads((_completed(job_id) / "events.json").read_text())

    @app.get("/v1/jobs/{job_id}/clips/{event_id}")
    def get_job_clip(job_id: str, event_id: str):
        return _clip(_dir(jobs, job_id), event_id)

    @app.post("/v1/jobs/{job_id}/reviews")
    def post_reviews(job_id: str, body: ReviewsIn):
        d = _completed(job_id)
        try:
            with review_lock:
                return dataset.save_reviews(d, [r.model_dump(exclude_none=True) for r in body.reviews])
        except ValueError as e:
            raise _bad(str(e)) from e

    @app.get("/v1/jobs/{job_id}/reviews")
    def get_reviews(job_id: str):
        d = _completed(job_id)
        reviews = dataset.load_reviews(d)
        return {"reviews": reviews, "metrics": evaluate_review(json.loads((d / "events.json").read_text()), reviews)}

    @app.post("/v1/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str):
        d = _dir(jobs, job_id)
        if job_id in active or _status(job_id)["state"] not in ("failed", "paused"):
            raise HTTPException(409, "only a failed or paused job can be retried")
        (d / "error.txt").unlink(missing_ok=True)
        if not enqueue("scan" if db_state(d) is None else "resume", job_id):
            raise HTTPException(409, "job is already queued")
        return {"job_id": job_id, "state": "queued"}

    @app.post("/v1/datasets", status_code=202)
    def create_dataset(body: DatasetIn):
        if not body.name.strip() or not body.job_ids:
            raise _bad("name and job_ids are required")
        for j in body.job_ids:
            _completed(j)  # 404 unknown, 409 not completed
        ds_id = "ds_" + uuid.uuid4().hex[:12]
        (dsets / ds_id).mkdir(parents=True)
        _write_json(dsets / ds_id / "request.json", {"name": body.name, "job_ids": list(dict.fromkeys(body.job_ids)),
                                                     "include_rejected": body.include_rejected})
        enqueue("dataset", ds_id)
        return {"dataset_id": ds_id, "state": "queued"}

    @app.get("/v1/datasets/{dataset_id}")
    def get_dataset(dataset_id: str):
        d = _dir(dsets, dataset_id)
        manifest, err = d / "dataset.json", d / "error.txt"
        if manifest.exists():
            state = "completed"
        elif err.exists():
            state = "failed"
        else:
            state = active.get(dataset_id, "queued")
        return {"dataset_id": dataset_id, "state": state, "error": err.read_text() if err.exists() else None,
                "stats": json.loads(manifest.read_text())["stats"] if manifest.exists() else None}

    @app.get("/v1/datasets/{dataset_id}/manifest")
    def get_manifest(dataset_id: str):
        p = _dir(dsets, dataset_id) / "dataset.json"
        if not p.exists():
            raise HTTPException(409, "dataset is not completed")
        return json.loads(p.read_text())

    @app.get("/v1/datasets/{dataset_id}/clips/{name}")
    def get_dataset_clip(dataset_id: str, name: str):
        return _clip(_dir(dsets, dataset_id), name)

    return app
