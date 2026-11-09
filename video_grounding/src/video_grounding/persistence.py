"""SQLite job store (source of truth). Plain functions over one sqlite3 connection."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import GroundingResult, Query, VideoInfo, Window

SCHEMA = """
create table if not exists jobs(job_id text primary key, video text, video_fingerprint text, config_hash text,
  model_revision text, state text, created_at text, updated_at text, queries text, video_info text);
create table if not exists windows(key text primary key, job_id text, query_id text, window_id text,
  start_us integer, end_us integer, sampling_profile text, model_revision text, fps real, max_frames integer,
  clip_path text, clip_origin_sec real, state text, attempts integer default 0, error text, oom_log text default '');
create table if not exists predictions(key text primary key, json text);
create table if not exists events(event_id text primary key, query_id text, json text);
create table if not exists artifacts(path text primary key, kind text, sha256 text);
"""
DONE = ("succeeded", "permanent_failed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _us(sec: float) -> int:
    return round(sec * 1e6)


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def window_key(job_id: str, query_id: str, start_sec: float, end_sec: float, profile: str, revision: str) -> str:
    return "|".join((job_id, query_id, str(_us(start_sec)), str(_us(end_sec)), profile, revision))


# ---- jobs
def create_job(conn, job_id: str, video: str, info: VideoInfo, config_hash: str, revision: str,
               queries: list[Query]) -> None:
    with conn:
        conn.execute("insert into jobs values(?,?,?,?,?,?,?,?,?,?)",
                     (job_id, video, info.fingerprint, config_hash, revision, "created", _now(), _now(),
                      json.dumps([dataclasses.asdict(q) for q in queries]), json.dumps(dataclasses.asdict(info))))


def get_job(conn) -> dict:
    row = conn.execute("select * from jobs").fetchone()
    if row is None:
        raise LookupError("no job in database")
    d = dict(row)
    d["queries"] = [Query(**q) for q in json.loads(d["queries"])]
    d["video_info"] = VideoInfo(**json.loads(d["video_info"]))
    return d


def set_job_state(conn, job_id: str, state: str) -> None:
    with conn:
        conn.execute("update jobs set state=?, updated_at=? where job_id=?", (state, _now(), job_id))


# ---- windows
def reset_running(conn, job_id: str) -> None:
    """Crash recovery: windows left running (or mid-retry) go back to pending."""
    with conn:
        conn.execute("update windows set state='pending' where job_id=? and state in ('running','retryable_failed')",
                     (job_id,))


def get_window(conn, key: str) -> dict | None:
    row = conn.execute("select * from windows where key=?", (key,)).fetchone()
    return dict(row) if row else None


def add_window(conn, key: str, job_id: str, query_id: str, w: Window, revision: str) -> None:
    with conn:
        conn.execute("insert or ignore into windows values(?,?,?,?,?,?,?,?,?,?,?,?,'pending',0,null,'')",
                     (key, job_id, query_id, w.window_id, _us(w.source_start_sec), _us(w.source_end_sec),
                      w.sampling_profile, revision, w.fps, w.max_frames, w.clip_path, w.clip_origin_sec))


def update_window(conn, key: str, **fields) -> None:
    with conn:
        conn.execute(f"update windows set {','.join(f'{k}=?' for k in fields)} where key=?", (*fields.values(), key))


def log_oom(conn, key: str, old: int, new: int) -> None:
    with conn:
        conn.execute("update windows set oom_log=oom_log||?, max_frames=? where key=?", (f"{old}->{new};", new, key))


def save_prediction(conn, key: str, result: GroundingResult) -> None:
    """Prediction insert and window=succeeded commit together or not at all."""
    with conn:
        conn.execute("insert or replace into predictions values(?,?)", (key, json.dumps(dataclasses.asdict(result))))
        conn.execute("update windows set state='succeeded', error=null where key=?", (key,))


def _window(row) -> Window:
    return Window(row["window_id"], row["start_us"] / 1e6, row["end_us"] / 1e6, row["clip_path"] or "",
                  row["clip_origin_sec"], row["fps"], row["max_frames"], row["sampling_profile"])


def _result(js: str) -> GroundingResult:
    d = json.loads(js)
    iv = d["predicted_local_interval"]
    return GroundingResult(d["window_id"], d["query_id"], d["model_id"], tuple(d["probabilities"]),
                           tuple(d["sample_source_pts"]), tuple(iv) if iv else None, d["alignment_status"],
                           d["raw_response"])


def load_pairs(conn, query_id: str, profile: str | None = None) -> list[tuple[Window, GroundingResult]]:
    rows = conn.execute("select w.*, p.json as pjson from windows w join predictions p on p.key=w.key "
                        "where w.state='succeeded' and w.query_id=? order by w.start_us, w.end_us, w.sampling_profile",
                        (query_id,)).fetchall()
    return [(_window(r), _result(r["pjson"])) for r in rows if profile in (None, r["sampling_profile"])]


def coverage_gaps(conn) -> list[dict]:
    rows = conn.execute("select * from windows where state='permanent_failed' "
                        "order by query_id, start_us, sampling_profile").fetchall()
    return [{"query_id": r["query_id"], "window_id": r["window_id"], "start_sec": r["start_us"] / 1e6,
             "end_sec": r["end_us"] / 1e6, "reason": r["error"]} for r in rows]


def first_model_id(conn) -> str | None:
    row = conn.execute("select json from predictions limit 1").fetchone()
    return json.loads(row[0])["model_id"] if row else None


def stats(conn) -> dict:
    counts: dict[str, int] = {}
    for r in conn.execute("select sampling_profile p, state s, count(*) n from windows group by p, s"):
        counts[f"{r['p']}.{r['s']}"] = r["n"]
    ooms = sum(r[0].count("->") for r in conn.execute("select oom_log from windows"))
    peak, ms = 0, 0.0
    for (js,) in conn.execute("select json from predictions"):
        rr = json.loads(js)["raw_response"]
        peak, ms = max(peak, rr.get("peak_vram_bytes") or 0), ms + (rr.get("inference_ms") or 0.0)
    failed = conn.execute("select count(*) from windows where state='permanent_failed'").fetchone()[0]
    retries = conn.execute("select coalesce(sum(attempts),0) from windows").fetchone()[0]
    return {"window_counts": counts, "permanent_failed": failed, "failed_attempts": retries,
            "oom_downgrades": ooms, "peak_vram_bytes": peak, "inference_ms_total": ms}


# ---- outputs
def write_predictions_jsonl(conn, path: str | Path, backend: str) -> None:
    """Regenerated from SQLite on every call (never appended)."""
    rows = conn.execute("select w.*, p.json as pjson from windows w left join predictions p on p.key=w.key "
                        "order by w.start_us, w.end_us, w.sampling_profile, w.query_id").fetchall()
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        for r in rows:
            res = _result(r["pjson"]) if r["pjson"] else None
            rr = res.raw_response if res else {}
            rec = {"job_id": r["job_id"], "query_id": r["query_id"], "window_id": r["window_id"],
                   "source_start_sec": r["start_us"] / 1e6, "source_end_sec": r["end_us"] / 1e6,
                   "sampled_pts": list(res.sample_source_pts) if res else [], "fps_request": r["fps"],
                   "fps_actual": rr.get("fps_actual"), "resolution": rr.get("resolution"),
                   "probabilities": list(res.probabilities) if res else [],
                   "raw_interval": list(res.predicted_local_interval) if res and res.predicted_local_interval else None,
                   "context_tokens": rr.get("context_tokens"), "inference_ms": rr.get("inference_ms"),
                   "peak_vram_bytes": rr.get("peak_vram_bytes"), "backend": backend,
                   "model_revision": r["model_revision"], "status": r["state"], "error": r["error"],
                   "sampling_profile": r["sampling_profile"], "clip_origin_sec": r["clip_origin_sec"],
                   "score_bounds": rr.get("score_bounds"), "alignment_status": res.alignment_status if res else None,
                   "model_id": res.model_id if res else None, "max_frames": r["max_frames"], "oom_log": r["oom_log"]}
            f.write(json.dumps(rec) + "\n")
    os.replace(tmp, path)


def save_events(conn, events: list) -> None:
    with conn:
        conn.execute("delete from events")
        conn.executemany("insert into events values(?,?,?)",
                         [(e.event_id, e.query_id, json.dumps(dataclasses.asdict(e))) for e in events])


def add_artifact(conn, path: str | Path, kind: str, rel: str) -> None:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with conn:
        conn.execute("insert or replace into artifacts values(?,?,?)", (rel, kind, h.hexdigest()))
