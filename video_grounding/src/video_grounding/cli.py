"""video-grounding CLI: probe | scan | resume | export | eval | serve | review | dataset."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .models import Query, Window
from .settings import Settings, load_settings


def _settings(path: str | None) -> Settings:
    return load_settings(path) if path else Settings()


def _probe(a) -> dict:
    from . import cutter, probe
    from .adapters.base import make_backend

    st = _settings(a.config)
    info = probe.probe_video(a.video)
    backend = make_backend(st)
    dur = min(10.0, info.duration_sec)
    w = Window("probe", 0.0, dur, "", 0.0, 1.0, 8)
    backend.load()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            if backend.needs_clip:
                clip = str(Path(tmp) / "probe.mp4")
                w = Window("probe", 0.0, dur, clip, cutter.cut_window_clip(a.video, 0.0, dur, clip, info), 1.0, 8)
            r = backend.ground(w, "probe", a.prompt)
    finally:
        backend.unload()
    return {"video": info.__dict__, "model_id": backend.model_id, "model_revision": backend.model_revision,
            "sample_source_pts": r.sample_source_pts, "probabilities": r.probabilities,
            "alignment_status": r.alignment_status, "raw_response": r.raw_response}


def _scan(a) -> dict:
    from .scheduler import run_scan

    if a.prompt_file:
        queries = [Query(q["query_id"], q["text"]) for q in json.loads(Path(a.prompt_file).read_text())]
    else:
        queries = [Query("q1", a.prompt)]
    return run_scan(a.video, queries, _settings(a.config), a.out)


def _resume(a) -> dict:
    from .scheduler import resume

    return resume(a.job)


def _export(a) -> dict:
    from .scheduler import export

    return export(a.job, high=a.threshold, low=a.low)


def _eval(a) -> dict:
    from .evaluation import evaluate, evaluate_review

    pred = json.loads(Path(a.pred).read_text())
    if a.reviews:
        return evaluate_review(pred, json.loads(Path(a.reviews).read_text()))
    return evaluate(pred, json.loads(Path(a.gt).read_text()))


def _serve(a) -> None:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(load_settings(a.config), a.jobs_root, media_root=a.media_root), host=a.host, port=a.port)


def _review(a) -> dict:
    from .dataset import save_reviews

    return save_reviews(a.job, json.loads(Path(a.reviews).read_text()))


def _dataset(a) -> dict:
    from .dataset import build_dataset

    return build_dataset(a.jobs, a.out, a.name, a.include_rejected)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="video-grounding")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="probe a video, load the backend, ground one short window")
    p.add_argument("--video", required=True), p.add_argument("--config")
    p.add_argument("--prompt", default="a person moving")
    p.set_defaults(fn=_probe)
    p = sub.add_parser("scan", help="scan a video for events matching the prompt(s)")
    p.add_argument("--video", required=True), p.add_argument("--config"), p.add_argument("--out", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt"), g.add_argument("--prompt-file", help="JSON list of {query_id, text}")
    p.set_defaults(fn=_scan)
    p = sub.add_parser("resume", help="continue an interrupted job")
    p.add_argument("--job", required=True)
    p.set_defaults(fn=_resume)
    p = sub.add_parser("export", help="re-fuse and re-export from stored predictions (no model calls)")
    p.add_argument("--job", required=True), p.add_argument("--threshold", type=float, help="high threshold")
    p.add_argument("--low", type=float)
    p.set_defaults(fn=_export)
    p = sub.add_parser("eval", help="score events.json against ground truth or reviewer decisions")
    p.add_argument("--pred", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--gt", help="labelled events: {events: [{query_id, start_sec, end_sec}]}")
    g.add_argument("--reviews", help="JSON list of {event_id, accepted, start_sec?, end_sec?}")
    p.set_defaults(fn=_eval)
    p = sub.add_parser("serve", help="HTTP API (needs the `server` extra)")
    p.add_argument("--config", required=True), p.add_argument("--jobs-root", required=True)
    p.add_argument("--host", default="127.0.0.1"), p.add_argument("--port", type=int, default=8800)
    p.add_argument("--media-root", help="local video paths must resolve inside this directory")
    p.set_defaults(fn=_serve)
    p = sub.add_parser("review", help="store reviewer decisions for a finished job")
    p.add_argument("--job", required=True), p.add_argument("--reviews", required=True, help="JSON list of {event_id, accepted, start_sec?, end_sec?}")
    p.set_defaults(fn=_review)
    p = sub.add_parser("dataset", help="compile reviewed events of finished jobs into a dataset")
    p.add_argument("--jobs", required=True, nargs="+"), p.add_argument("--out", required=True)
    p.add_argument("--name", required=True), p.add_argument("--include-rejected", action="store_true")
    p.set_defaults(fn=_dataset)
    a = ap.parse_args(argv)
    out = a.fn(a)
    if a.cmd in ("eval", "probe", "review", "dataset"):
        print(json.dumps(out, indent=2, ensure_ascii=False))
    elif a.cmd != "serve":
        print(f"{a.cmd}: {len(out['events'])} events, scan_complete={out['scan_complete']}, "
              f"coverage_gaps={len(out['coverage_gaps'])}")
    return 0
