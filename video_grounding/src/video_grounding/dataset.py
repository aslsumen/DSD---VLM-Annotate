"""Reviewer decisions (reviews.json per job) and the dataset compiled from reviewed jobs."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import cutter, persistence as P
from .evaluation import evaluate_review
from .scheduler import _write_json
from .settings import load_settings


def load_reviews(job_dir: str | Path) -> list[dict]:
    p = Path(job_dir) / "reviews.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_reviews(job_dir: str | Path, reviews: list[dict]) -> dict:
    """Validate, merge into reviews.json by event_id (latest wins), return evaluate_review metrics."""
    jd = Path(job_dir)
    doc = json.loads((jd / "events.json").read_text())
    ev = {e["event_id"]: e for e in doc["events"]}
    clean = {}
    for r in reviews:
        e = ev.get(r.get("event_id"))
        if e is None:
            raise ValueError(f"unknown event_id: {r.get('event_id')!r}")
        if not isinstance(r.get("accepted"), bool):
            raise ValueError(f"{r['event_id']}: accepted must be true or false")
        c = {"event_id": r["event_id"], "accepted": r["accepted"]}
        for k in ("start_sec", "end_sec"):
            if r.get(k) is not None:
                if isinstance(r[k], bool) or not isinstance(r[k], (int, float)):
                    raise ValueError(f"{r['event_id']}: {k} must be a number")
                c[k] = float(r[k])
        s, t = c.get("start_sec", e["event_start_sec"]), c.get("end_sec", e["event_end_sec"])
        if not 0 <= s < t <= doc["video_duration_sec"]:
            raise ValueError(f"{r['event_id']}: need 0 <= start < end <= {doc['video_duration_sec']}, got {s}, {t}")
        clean[c["event_id"]] = c
    merged = {r["event_id"]: r for r in load_reviews(jd)} | clean
    tmp = jd / "reviews.json.tmp"
    tmp.write_text(json.dumps(list(merged.values()), indent=2))
    os.replace(tmp, jd / "reviews.json")
    return evaluate_review(doc, list(merged.values()))


def build_dataset(job_dirs: list, out_dir: str | Path, name: str, include_rejected: bool = False) -> dict:
    """Compile reviewed events of finished jobs into out_dir/dataset.json + out_dir/clips/.

    Unreviewed events are skipped. n_rejected counts rejected reviews whether or not they are included.
    Clip file names are <job_id>_<event_id>.mp4: event ids repeat across videos (query + times + config).
    """
    out = Path(out_dir)
    (out / "clips").mkdir(parents=True, exist_ok=True)
    videos, anns, model, n_unreviewed, n_rejected = [], [], None, 0, 0
    for jd in map(Path, job_dirs):
        doc = json.loads((jd / "events.json").read_text())
        model = model or (doc["model_id"], doc["model_revision"])  # ponytail: first job's model; mixed models not flagged
        reviews = {r["event_id"]: r for r in load_reviews(jd)}
        conn = P.connect(jd / "job.sqlite")
        try:
            info = P.get_job(conn)["video_info"]
        finally:
            conn.close()
        ex = load_settings(jd / "config.yaml").export
        dur = doc["video_duration_sec"]
        videos.append({"video": doc["video"], "job_id": doc["job_id"], "duration_sec": dur,
                       "scan_complete": doc["scan_complete"]})
        for e in doc["events"]:
            r = reviews.get(e["event_id"])
            if r is None:
                n_unreviewed += 1
                continue
            n_rejected += not r["accepted"]
            if not r["accepted"] and not include_rejected:
                continue
            s, t = r.get("start_sec", e["event_start_sec"]), r.get("end_sec", e["event_end_sec"])
            adjusted = abs(s - e["event_start_sec"]) > 1e-6 or abs(t - e["event_end_sec"]) > 1e-6
            rel = f"clips/{doc['job_id']}_{e['event_id']}.mp4"
            have = jd / "clips" / f"{e['event_id']}.mp4"
            if have.exists() and not adjusted:
                shutil.copy2(have, out / rel)
            else:
                cs, ce = ((max(0.0, s - ex.pre_roll), min(dur, t + ex.post_roll)) if adjusted
                          else (e["clip_start_sec"], e["clip_end_sec"]))
                cutter.export_event_clip(doc["video"], cs, ce, str(out / rel), info, crf=ex.crf, preset=ex.preset)
            anns.append({"video": doc["video"], "job_id": doc["job_id"], "query_id": e["query_id"],
                         "prompt": e["query"], "start_s": s, "end_s": t,
                         "status": "accepted" if r["accepted"] else "rejected", "engine_event_id": e["event_id"],
                         "clip": rel, "adjusted": adjusted, "raw_score_max": e["raw_score_max"]})
    stats = {"n_annotations": len(anns), "n_accepted": sum(a["status"] == "accepted" for a in anns),
             "n_rejected": n_rejected, "n_unreviewed": n_unreviewed}
    _write_json(out / "dataset.json", {
        "dataset": name, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model[0] if model else None, "model_revision": model[1] if model else None,
        "videos": videos, "annotations": anns, "stats": stats})
    return stats
