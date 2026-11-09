"""Evaluation of events.json: against ground truth (same query_id only) or against reviewer decisions."""
from __future__ import annotations

import numpy as np


def _iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


def _match(preds: list[dict], gts: list[dict]) -> list[tuple[float, dict, dict]]:
    """One-to-one greedy matching by descending IoU (IoU > 0), within one query."""
    cand = sorted(((_iou((p["event_start_sec"], p["event_end_sec"]), (g["start_sec"], g["end_sec"])), i, j)
                   for i, p in enumerate(preds) for j, g in enumerate(gts)), key=lambda c: (-c[0], c[1], c[2]))
    used_p, used_g, out = set(), set(), []
    for iou, i, j in cand:
        if iou > 0 and i not in used_p and j not in used_g:
            used_p.add(i), used_g.add(j)
            out.append((iou, preds[i], gts[j]))
    return out


def evaluate(pred: dict, gt: dict, iou_thresholds=(0.3, 0.5, 0.7)) -> dict:
    qids = {e["query_id"] for e in pred["events"]} | {e["query_id"] for e in gt["events"]}
    matches = []
    for q in sorted(qids):
        matches += _match([e for e in pred["events"] if e["query_id"] == q],
                          [e for e in gt["events"] if e["query_id"] == q])
    n_gt, n_pred = len(gt["events"]), len(pred["events"])
    lo = min(iou_thresholds)
    good = [m for m in matches if m[0] >= lo - 1e-12]
    p = lambda xs, q: float(np.percentile(xs, q)) if xs else None  # noqa: E731
    s_err = [abs(pe["event_start_sec"] - g["start_sec"]) for _, pe, g in good]
    e_err = [abs(pe["event_end_sec"] - g["end_sec"]) for _, pe, g in good]
    out = {"n_gt": n_gt, "n_pred": n_pred,
           "event_recall": len(good) / n_gt if n_gt else 0.0,
           "event_precision": len(good) / n_pred if n_pred else 0.0,
           "temporal_miou": sum(m[0] for m in matches) / n_gt if n_gt else 0.0,
           "start_err_p50": p(s_err, 50), "start_err_p90": p(s_err, 90),
           "end_err_p50": p(e_err, 50), "end_err_p90": p(e_err, 90),
           "coverage_gaps": len(pred.get("coverage_gaps", []))}
    for t in iou_thresholds:
        out[f"R@IoU{t}"] = sum(m[0] >= t - 1e-12 for m in matches) / n_gt if n_gt else 0.0
    return out


def evaluate_review(pred: dict, reviews: list[dict], tolerance_sec: float = 2.0) -> dict:
    """Score events.json from reviewer decisions, with no ground truth.

    reviews: [{event_id, accepted: bool, start_sec?, end_sec?}]. start/end are the reviewer's
    adjusted boundaries (REV-2); missing means unchanged. Recall is not measurable this way:
    events the engine missed are never shown to a reviewer.
    A clip counts as complete if it misses at most tolerance_sec at each end: reviewers fix small
    boundary errors anyway, and VideoJev's score cells are 2 s wide at 1 FPS.
    """
    ev = {e["event_id"]: e for e in pred["events"]}
    unknown = [r["event_id"] for r in reviews if r["event_id"] not in ev]
    if unknown:
        raise ValueError(f"reviews for unknown event_id: {unknown[:5]}")
    acc = [(ev[r["event_id"]], r) for r in reviews if r["accepted"]]
    span = lambda e, r: (r.get("start_sec", e["event_start_sec"]), r.get("end_sec", e["event_end_sec"]))  # noqa: E731
    tol = tolerance_sec + 1e-6
    inside = [e["clip_start_sec"] - tol <= span(e, r)[0] and span(e, r)[1] <= e["clip_end_sec"] + tol
              for e, r in acc]
    adj = [abs(span(e, r)[0] - e["event_start_sec"]) for e, r in acc] + \
          [abs(span(e, r)[1] - e["event_end_sec"]) for e, r in acc]
    p = lambda xs, q: float(np.percentile(xs, q)) if xs else None  # noqa: E731
    per_query = {}
    for q in sorted({e["query_id"] for e in ev.values()}):
        rq = [r for r in reviews if ev[r["event_id"]]["query_id"] == q]
        per_query[q] = {"reviewed": len(rq), "accepted": sum(r["accepted"] for r in rq),
                        "accept_rate": sum(r["accepted"] for r in rq) / len(rq) if rq else None}
    return {"n_candidates": len(ev), "n_reviewed": len(reviews), "n_accepted": len(acc),
            "accept_rate": len(acc) / len(reviews) if reviews else None,
            "complete_clip_rate": sum(inside) / len(acc) if acc else None,
            "boundary_adjust_p50": p(adj, 50), "boundary_adjust_p90": p(adj, 90),
            "per_query": per_query}
