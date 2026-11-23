"""Charades-STA benchmark: a seeded random subset of test videos through scan -> refine -> Gemini verify, then KPIs.

Data (HF lmms-lab/charades_sta) in DATA_DIR: test.json (data/test-*.parquet as a JSON list of
{video, caption, timestamp}) and zips/part_*.zip (Charades_v1_480_part_*.zip).

  python scripts/charades_sta.py run   DATA_DIR N CONFIG [RUNS]  # first N videos of a seed-0 shuffle; reruns skip finished ones
  python scripts/charades_sta.py score DATA_DIR [RUNS]           # KPIs over every finished video, JSON on stdout
RUNS (default "runs") names the output folder under DATA_DIR, one per config being compared.
"""
from __future__ import annotations

import json
import random
import shutil
import statistics
import sys
import time
import zipfile
from pathlib import Path

from video_grounding.evaluation import _iou, _match, evaluate, evaluate_review


def _by_video(data: Path) -> dict[str, list[tuple[int, dict]]]:
    by: dict[str, list[tuple[int, dict]]] = {}
    for i, r in enumerate(json.loads((data / "test.json").read_text())):
        by.setdefault(r["video"], []).append((i, r))
    return by


def run(data: Path, n: int, config: str, runs: str = "runs") -> None:
    from video_grounding.adapters.base import make_backend
    from video_grounding.models import Query
    from video_grounding.scheduler import run_scan
    from video_grounding.settings import load_settings
    from video_grounding.verifier import GeminiVerifier

    by = _by_video(data)
    vids = sorted(by)
    random.Random(0).shuffle(vids)
    zips = {}
    for z in map(zipfile.ZipFile, sorted(data.glob("zips/part_*.zip"))):
        zips.update({name.rsplit("/", 1)[-1]: (z, name) for name in z.namelist()})
    st = load_settings(config)
    backend = make_backend(st)
    verifier = GeminiVerifier(st.verify) if st.verify.enabled else None
    (data / "videos").mkdir(exist_ok=True)
    for k, v in enumerate(vids[:n]):
        stem = v.removesuffix(".mp4")
        out = data / runs / stem
        if (out / "events.json").exists():
            continue
        shutil.rmtree(out, ignore_errors=True)  # a crashed attempt restarts clean
        src = data / "videos" / v
        if not src.exists():
            z, name = zips[v]
            src.write_bytes(z.read(name))
        t = time.time()
        try:
            run_scan(str(src), [Query(f"{stem}_{i}", r["caption"]) for i, r in by[v]], st, out,
                     backend=backend, keep_loaded=True, verifier=verifier)
        except Exception as exc:  # one bad video must not stop the batch; score() counts it as missing
            print(json.dumps({"video": v, "k": k, "failed": repr(exc)[:300]}), flush=True)
            continue
        print(json.dumps({"video": v, "k": k, "wall_s": round(time.time() - t, 2)}), flush=True)


def _kpis(preds: list[dict], gts: list[dict]) -> dict:
    """Engine KPIs, plus an oracle reviewer: it accepts an event matched to GT at IoU >= 0.3 and drags its
    boundaries to the GT span, so complete_clip_rate is the share of accepted clips holding GT within 2 s."""
    m = evaluate({"events": preds}, {"events": gts})
    pq, gq = {}, {}
    for e in preds:
        pq.setdefault(e["query_id"], []).append(e)
    for g in gts:
        gq.setdefault(g["query_id"], []).append(g)
    reviews = [{"event_id": p["event_id"], "accepted": True, "start_sec": g["start_sec"], "end_sec": g["end_sec"]}
               for q in gq for iou, p, g in _match(pq.get(q, []), gq[q]) if iou >= 0.3]
    r = evaluate_review({"events": preds}, reviews)
    top1 = [max(_iou((p["event_start_sec"], p["event_end_sec"]), (g["start_sec"], g["end_sec"]))
                for p in [max(pq[q], key=lambda e: e["raw_score_max"])] for g in gq[q]) if q in pq else 0.0
            for q in gq]  # standard Charades-STA R1: the highest-scoring event per query, IoU 0 when none
    out = {k: m[k] for k in ("n_pred", "event_recall", "event_precision", "temporal_miou", "R@IoU0.3", "R@IoU0.5",
                             "R@IoU0.7", "start_err_p50", "start_err_p90", "end_err_p50", "end_err_p90")}
    out.update(complete_clip_rate=r["complete_clip_rate"], boundary_adjust_mean=r["boundary_adjust_mean"],
               preds_per_query=len(preds) / len(gts),
               queries_without_pred=sum(q not in pq for q in gq) / len(gq),
               R1_mIoU=statistics.fmean(top1), **{f"R1@{t}": sum(x >= t for x in top1) / len(top1)
                                                  for t in (0.3, 0.5, 0.7)})
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in out.items()}


def score(data: Path, runs: str = "runs") -> dict:
    by = _by_video(data)
    docs = {p.parent.name: json.loads(p.read_text()) for p in sorted(data.glob(f"{runs}/*/events.json"))}
    gts = [{"query_id": f"{v.removesuffix('.mp4')}_{i}", "start_sec": float(r["timestamp"][0]),
            "end_sec": float(r["timestamp"][1])} for v, rows in by.items() if v.removesuffix(".mp4") in docs
           for i, r in rows]
    kept = [e for d in docs.values() for e in d["events"]]
    allev = kept + [e for d in docs.values() for e in d.get("rejected_events", [])]
    p_of = lambda e: (e.get("verdict") or {}).get("p_present")  # noqa: E731
    res = {"n_videos": len(docs), "n_queries": len(gts),
           "video_sec": round(sum(d["video_duration_sec"] for d in docs.values()), 1),
           "before_verify": _kpis(allev, gts), "after_verify": _kpis(kept, gts),
           "verify_sweep": {t: _kpis([e for e in allev if p_of(e) is None or p_of(e) >= t], gts)
                            for t in (0.3, 0.5, 0.7)}}
    gt_len = {g["query_id"]: g["end_sec"] - g["start_sec"] for g in gts}
    bins = {"<5s": (0, 5), "5-10s": (5, 10), ">=10s": (10, 1e9)}
    res["by_gt_length"] = {}
    for name, (lo, hi) in bins.items():
        qs = {q for q, n in gt_len.items() if lo <= n < hi}
        if not qs:
            continue
        sub = lambda evs: [e for e in evs if e["query_id"] in qs]  # noqa: E731
        res["by_gt_length"][name] = {"n": len(qs), "before": _kpis(sub(allev), [g for g in gts if g["query_id"] in qs]),
                                     "after": _kpis(sub(kept), [g for g in gts if g["query_id"] in qs])}
    # Gemini as a classifier: positive = event matched to GT at IoU >= 0.3
    gq = {g["query_id"]: g for g in gts}
    hit = lambda e: _iou((e["event_start_sec"], e["event_end_sec"]),  # noqa: E731
                         (gq[e["query_id"]]["start_sec"], gq[e["query_id"]]["end_sec"])) >= 0.3
    ver = [e for e in allev if p_of(e) is not None]
    res["gemini"] = {"verdicts": len(ver), "not_verified": len(allev) - len(ver),
                     "true_events_kept": sum(hit(e) and p_of(e) >= 0.5 for e in ver),
                     "true_events": sum(hit(e) for e in ver),
                     "false_events_removed": sum(not hit(e) and p_of(e) < 0.5 for e in ver),
                     "false_events": sum(not hit(e) for e in ver)}
    tm = [json.loads((data / runs / v / "manifest.json").read_text()).get("timings", {}) for v in docs]
    res["timing_mean_s"] = {k: round(statistics.fmean(t.get(k, 0) for t in tm), 2)
                            for k in ("scan_s", "refine_s", "verify_s", "export_s")}
    # RTF as the product runs it (verify off in the adapter); model load is not in the manifest
    res["rtf_no_verify"] = round(sum(t.get(k, 0) for t in tm for k in ("scan_s", "refine_s", "export_s"))
                                 / res["video_sec"], 2)
    return res


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4], *sys.argv[5:6])
    else:
        print(json.dumps(score(Path(sys.argv[2]), *sys.argv[3:4]), indent=1))
