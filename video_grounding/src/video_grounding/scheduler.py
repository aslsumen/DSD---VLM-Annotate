"""Job orchestration: scan -> refine -> export, with crash-safe resume. SQLite is the source of truth.

A permanently failed window is never read as "no event": it becomes a coverage gap and makes
events.json `scan_complete` false.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import yaml

from . import fusion, persistence as P, refinement
from .adapters.base import make_backend
from .models import BackendOOM, Query, VideoInfo, Window
from .sampler import plan_windows
from .settings import Settings, config_hash, dump_settings, load_settings


class ResumeMismatch(ValueError):
    """Config, model revision or source video changed since the job was created."""


@dataclass
class _Job:
    out: Path
    conn: object
    job_id: str
    info: VideoInfo
    settings: Settings
    chash: str
    queries: list[Query]
    revision: str
    video: str
    backend: object = None
    verifier: object = None
    timings: dict = field(default_factory=dict)


def _write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _wid(profile: str, i: int, s: float, e: float) -> str:
    return f"w{i:05d}" if profile == "coarse" else f"r_{round(s * 1000)}_{round(e * 1000)}"


def _coarse_windows(job: _Job) -> list[Window]:
    c = job.settings.coarse
    return [Window(_wid("coarse", i, s, e), s, e, "", s, c.fps, c.max_frames, "coarse")
            for i, (s, e) in enumerate(plan_windows(job.info.duration_sec, c.window_seconds, c.stride_seconds))]


def _refine_windows(job: _Job, tiles: list[tuple[float, float]]) -> list[Window]:
    r = job.settings.refine
    return [Window(_wid("refine", 0, s, e), s, e, "", s, r.fps, r.max_frames, "refine") for s, e in tiles]


def _key(job: _Job, q: Query, w: Window) -> str:
    return P.window_key(job.job_id, q.query_id, w.source_start_sec, w.source_end_sec, w.sampling_profile, job.revision)


def _ground_one(job: _Job, q: Query, w: Window) -> None:
    conn, st, key = job.conn, job.settings, _key(job, q, w)
    row = P.get_window(conn, key)
    if row is None:
        P.add_window(conn, key, job.job_id, q.query_id, w, job.revision)
        row = P.get_window(conn, key)
    if row["state"] in P.DONE:
        return
    mf, attempts = min(w.max_frames, row["max_frames"]), row["attempts"]
    P.update_window(conn, key, clip_path=w.clip_path, clip_origin_sec=w.clip_origin_sec)
    while True:
        P.update_window(conn, key, state="running", max_frames=mf)
        try:
            res = job.backend.ground(replace(w, max_frames=mf), q.query_id, q.text)
        except BackendOOM as e:
            lower = next((v for v in st.retry.oom_ladder if v < mf), None)
            if lower is None:
                P.update_window(conn, key, state="permanent_failed", error=f"OOM at {mf} frames, ladder exhausted: {e}")
                return
            P.log_oom(conn, key, mf, lower)
            mf = lower
        except Exception as e:  # noqa: BLE001  (BaseException = crash/interrupt: leave "running" for resume)
            attempts += 1
            err = f"{type(e).__name__}: {e}"
            if attempts >= st.retry.max_attempts:
                P.update_window(conn, key, state="permanent_failed", attempts=attempts, error=err)
                return
            P.update_window(conn, key, state="retryable_failed", attempts=attempts, error=err)
        else:
            if job.info.fps:  # backend can't know source fps; nearest-frame sampling error ≤ half a frame
                res.raw_response.setdefault("timestamp_error_sec", 0.5 / job.info.fps)
            P.save_prediction(conn, key, res)
            return


def _ground_all(job: _Job, windows: list[Window], queries: list[Query]) -> None:
    """Windows outer, queries inner: one clip / one encoding per window serves every query."""
    for w in windows:
        todo = [q for q in queries
                if (P.get_window(job.conn, _key(job, q, w)) or {"state": ""})["state"] not in P.DONE]
        if not todo:
            continue
        if job.backend.needs_clip:
            from . import cutter

            name = f"{w.sampling_profile}_{round(w.source_start_sec * 1000)}_{round(w.source_end_sec * 1000)}.mp4"
            path = job.out / "windows" / name
            path.parent.mkdir(exist_ok=True)
            origin = cutter.cut_window_clip(job.video, w.source_start_sec, w.source_end_sec, str(path), job.info)
            w = replace(w, clip_path=str(path), clip_origin_sec=origin)
        for q in todo:
            _ground_one(job, q, w)


def _events(job: _Job, q: Query, profile: str | None = None, settings: Settings | None = None):
    return fusion.events_for_query(P.load_pairs(job.conn, q.query_id, profile), q,
                                   duration=job.info.duration_sec, settings=settings or job.settings,
                                   model_revision=job.revision, config_hash=_hash(job, settings))


def _hash(job: _Job, settings: Settings | None) -> str:
    return job.chash if settings is None else config_hash(settings)


def _scan(job: _Job) -> None:
    P.set_job_state(job.conn, job.job_id, "scanning")
    _ground_all(job, _coarse_windows(job), job.queries)


def _refine(job: _Job) -> None:
    P.set_job_state(job.conn, job.job_id, "refining")
    st = job.settings
    if not st.refine.enabled:
        return
    for q in job.queries:
        spans = refinement.plan_spans(_events(job, q, "coarse"), job.info.duration_sec,
                                      coarse=st.coarse, refine=st.refine)
        tiles = [t for sp in spans for t in refinement.tile(sp.start, sp.end, st.refine.window_seconds)]
        _ground_all(job, _refine_windows(job, tiles), [q])
        for _ in range(64):  # Stage C; terminates because each pass grows a span toward max_span_seconds
            tiles, spans = refinement.extend_spans(spans, _events(job, q), job.info.duration_sec,
                                                   refine=st.refine, grid_seconds=st.fusion.grid_seconds)
            if not tiles:
                break
            _ground_all(job, _refine_windows(job, tiles), [q])


def _verdict_key(e, model: str) -> str:
    return f"{e.query_id}|{round(e.clip_start_sec * 1e6)}|{round(e.clip_end_sec * 1e6)}|{model}"


def _verify(job: _Job) -> None:
    """Stage V: ask Gemini whether each event clip really shows the query. Verdicts are cached in SQLite."""
    if not job.settings.verify.enabled:
        return
    P.set_job_state(job.conn, job.job_id, "verifying")
    for q in job.queries:
        for e in _events(job, q, None, job.settings):
            key = _verdict_key(e, job.settings.verify.model)
            if P.get_verdict(job.conn, key) is not None:
                continue
            try:
                v = job.verifier.verify(job.video, job.info, e.clip_start_sec, e.clip_end_sec, q.text)
            except Exception as exc:  # stays unverified: export flags it "not_verified", resume retries it
                print(f"verify {e.event_id} failed: {exc}", file=sys.stderr)
                if 429 in (getattr(exc, "code", None), getattr(exc, "status_code", None)):  # quota still exhausted after the SDK's retries
                    print("verify stopped: Gemini quota exhausted; resume the job later", file=sys.stderr)
                    return
                continue
            P.save_verdict(job.conn, key, v)


def _export(job: _Job, settings: Settings | None = None) -> dict:
    """Re-fuse stored predictions and write every output. Makes no model calls."""
    P.set_job_state(job.conn, job.job_id, "exporting")
    st = settings or job.settings
    t0 = time.perf_counter()
    gaps = P.coverage_gaps(job.conn)
    all_events, rejected, qdocs = [], [], []
    for q in job.queries:
        evs = sorted(_events(job, q, None, st), key=lambda e: -e.raw_score_max)  # reviewers see likely ones first
        if st.verify.enabled:  # Gemini only removes refined events; unverified ones stay for the reviewer
            for e in evs:
                e.verdict = P.get_verdict(job.conn, _verdict_key(e, st.verify.model))
                if e.verdict is None:
                    e.needs_review = True
                    e.review_reasons.append("not_verified")
            rejected += [e for e in evs if e.verdict and not e.verdict["present"]]
            evs = [e for e in evs if not (e.verdict and not e.verdict["present"])]
        if st.export.cut_clips:
            from . import cutter

            for e in evs:
                rel = f"clips/{e.event_id}.mp4"
                path = job.out / rel
                if not path.exists():
                    path.parent.mkdir(exist_ok=True)
                    cutter.export_event_clip(job.video, e.clip_start_sec, e.clip_end_sec, str(path), job.info,
                                             crf=st.export.crf, preset=st.export.preset)
                e.clip_path = rel
                P.add_artifact(job.conn, path, "clip", rel)
        all_events += evs
        qdocs.append({"query_id": q.query_id, "query": q.text,
                      "warnings": ["unsupported_modality_warning"] if fusion.unsupported_modality(q.text) else [],
                      "scan_complete": not any(g["query_id"] == q.query_id for g in gaps)})
    P.save_events(job.conn, all_events)
    doc = {"job_id": job.job_id, "video": job.video, "video_duration_sec": job.info.duration_sec,
           "backend": st.runtime.backend, "model_id": P.first_model_id(job.conn) or st.model.id,
           "model_revision": job.revision, "scan_complete": not gaps, "queries": qdocs,
           "events": [e.__dict__ for e in all_events], "coverage_gaps": gaps}
    if st.verify.enabled:
        doc["rejected_events"] = [e.__dict__ for e in rejected]  # audit trail; no clips are cut for these
    _write_json(job.out / "events.json", doc)
    P.write_predictions_jsonl(job.conn, job.out / "window_predictions.jsonl", st.runtime.backend)
    for name, kind in (("events.json", "events"), ("window_predictions.jsonl", "predictions")):
        P.add_artifact(job.conn, job.out / name, kind, name)
    job.timings["export_s"] = round(time.perf_counter() - t0, 3)
    _write_json(job.out / "manifest.json", {
        "job_id": job.job_id, "video": job.video, "video_fingerprint": job.info.fingerprint,
        "model_id": doc["model_id"], "model_revision": job.revision, "config_hash": config_hash(st),
        "python": sys.version.split()[0], "numpy": np.__version__, "timings": job.timings})
    _write_json(job.out / "metrics.json", {**P.stats(job.conn), "timings": job.timings,
                                           "coverage_gaps": len(gaps), "events": len(all_events)})
    P.set_job_state(job.conn, job.job_id, "completed")
    return doc


def _continue(job: _Job, keep_loaded: bool = False) -> dict:
    P.reset_running(job.conn, job.job_id)
    try:
        if job.settings.verify.enabled and job.verifier is None:  # fail on a missing key before hours of scanning
            from .verifier import GeminiVerifier

            job.verifier = GeminiVerifier(job.settings.verify)
        job.backend.load()
        for name, fn in (("scan_s", _scan), ("refine_s", _refine), ("verify_s", _verify)):
            t0 = time.perf_counter()
            fn(job)
            job.timings[name] = round(time.perf_counter() - t0, 3)
        return _export(job)
    except Exception:
        P.set_job_state(job.conn, job.job_id, "failed")
        raise
    except BaseException:  # KeyboardInterrupt / process-level crash: resumable
        P.set_job_state(job.conn, job.job_id, "paused")
        raise
    finally:
        if not keep_loaded:
            job.backend.unload()


def run_scan(video: str, queries: list[Query], settings: Settings, out_dir: str | Path, *,
             video_info: VideoInfo | None = None, backend=None, job_id: str | None = None,
             keep_loaded: bool = False, verifier=None) -> dict:
    out = Path(out_dir)
    if (out / "job.sqlite").exists():
        raise FileExistsError(f"{out} already holds a job; use resume")
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.yaml").write_text(dump_settings(settings))
    backend = backend or make_backend(settings)
    conn = P.connect(out / "job.sqlite")
    job_id = job_id or "job-" + time.strftime("%Y%m%d-%H%M%S")
    if video_info is None:
        from . import probe

        video_info = probe.probe_video(video)
    chash = config_hash(settings)
    P.create_job(conn, job_id, video, video_info, chash, backend.model_revision, queries)
    job = _Job(out, conn, job_id, video_info, settings, chash, queries, backend.model_revision, video, backend,
               verifier)
    return _continue(job, keep_loaded)


def _open(out_dir: str | Path, backend=None, video_info: VideoInfo | None = None, check: bool = True) -> _Job:
    out = Path(out_dir)
    conn = P.connect(out / "job.sqlite")
    row = P.get_job(conn)
    settings = load_settings(out / "config.yaml")
    if check:
        if config_hash(settings) != row["config_hash"]:
            raise ResumeMismatch("config.yaml changed since the job was created; start a new job")
        backend = backend or make_backend(settings)
        if backend.model_revision != row["model_revision"]:
            raise ResumeMismatch(f"model revision {backend.model_revision} != job {row['model_revision']}")
        if video_info is None:
            from . import probe

            video_info = probe.probe_video(row["video"])
        if video_info.fingerprint != row["video_fingerprint"]:
            raise ResumeMismatch("source video changed since the job was created; start a new job")
    return _Job(out, conn, row["job_id"], row["video_info"], settings,
                row["config_hash"], row["queries"], row["model_revision"], row["video"], backend)


def resume(out_dir: str | Path, *, backend=None, video_info: VideoInfo | None = None,
           keep_loaded: bool = False, verifier=None) -> dict:
    job = _open(out_dir, backend, video_info)
    job.verifier = verifier
    return _continue(job, keep_loaded)


def export(out_dir: str | Path, *, high: float | None = None, low: float | None = None) -> dict:
    """No model calls: re-fuse stored predictions (optionally with new thresholds) and re-export."""
    job = _open(out_dir, check=False)
    st = job.settings
    if high is not None or low is not None:
        fz = st.fusion.model_copy(update={k: v for k, v in (("high", high), ("low", low)) if v is not None})
        st = st.model_copy(update={"fusion": fz})
    return _export(job, st)
