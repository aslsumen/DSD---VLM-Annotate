"""Global probability fusion, hysteresis event extraction and completeness review flags.

Pure numpy and deterministic: inputs are sorted by window_id before summation, so result order
never matters. Fusion is a weighted MEAN, so overlapping windows can never inflate a score.
No calibrated confidence is ever produced; raw_score_max is the raw sigmoid output.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from .models import Event, GroundingResult, Query, Window, stable_event_id
from .settings import Settings

Pair = tuple[Window, GroundingResult]
_RANK = {"exact": 0, "estimated": 1, "unknown": 2}
_MODALITY = ("声音", "说话", "对白", "听到", "喊", "音乐", "sound", "audio", "says", "said", "speech",
             "speak", "hear", "music", "voice", "shout", "scream", "talk")


class Fused(NamedTuple):
    grid: np.ndarray        # global seconds
    score: np.ndarray       # fused probability, NaN where no window covers
    max_weight: np.ndarray  # max edge-distance weight (1 at window centre or video edge, 0 at an inner window edge)
    spacing: np.ndarray     # finest local sample spacing (s) over covering results; inf if uncovered


def unsupported_modality(query_text: str) -> bool:
    t = query_text.lower()
    return any(k in t for k in _MODALITY)


def _span(r: GroundingResult) -> tuple[float, float]:
    b = r.raw_response.get("score_bounds")
    return (b[0], b[-1]) if b else (r.sample_source_pts[0], r.sample_source_pts[-1])


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return x
    valid = ~np.isnan(x)
    ker = np.ones(k)
    num = np.convolve(np.where(valid, x, 0.0), ker, "same")
    cnt = np.convolve(valid.astype(float), ker, "same")
    out = np.full_like(x, np.nan)
    ok = valid & (cnt > 0)
    out[ok] = num[ok] / cnt[ok]
    return out


def fuse(pairs: list[Pair], *, duration: float, grid_seconds: float = 0.5, smooth_cells: int = 3,
         edge_weight_floor: float = 0.05) -> Fused:
    g = np.arange(0, duration + 1e-9, grid_seconds)
    num, den = np.zeros_like(g), np.zeros_like(g)
    maxw, spacing = np.zeros_like(g), np.full_like(g, np.inf)
    items = []
    for w, r in sorted(pairs, key=lambda p: (p[0].window_id, p[0].sampling_profile, p[0].source_start_sec)):
        lo, hi = _span(r)
        m = (g >= lo - 1e-9) & (g <= hi + 1e-9)
        if m.any():
            items.append((w, r, m, float(r.raw_response.get("fps_actual") or w.fps)))
    # Coarse windows find events; where denser (refine) sampling exists, only it sets the score and boundaries.
    best = np.zeros_like(g)
    for _, _, m, fps in items:
        best[m] = np.maximum(best[m], fps)
    for w, r, m, fps in items:
        m = m & (best <= fps * (1 + 1e-6))
        if not m.any():
            continue
        pts, pr = np.asarray(r.sample_source_pts, float), np.asarray(r.probabilities, float)
        lo, hi = _span(r)
        gm = g[m]
        half = max((w.source_end_sec - w.source_start_sec) / 2, 1e-9)
        # distance to a window edge; a window edge on the video edge truncates nothing, so it doesn't count
        d_lo = gm - w.source_start_sec if w.source_start_sec > grid_seconds else np.inf
        d_hi = w.source_end_sec - gm if w.source_end_sec < duration - grid_seconds else np.inf
        tri = np.clip(np.minimum(d_lo, d_hi) / half, 0, 1)
        wt = np.maximum(edge_weight_floor, tri)
        num[m] += wt * np.interp(gm, pts, pr)
        den[m] += wt
        maxw[m] = np.maximum(maxw[m], tri)
        if len(pts) > 1:
            k = np.clip(np.searchsorted(pts, gm) - 1, 0, len(pts) - 2)
            sp = pts[k + 1] - pts[k]
        else:
            sp = np.full(len(gm), hi - lo)
        spacing[m] = np.minimum(spacing[m], sp)
    score = np.full_like(g, np.nan)
    np.divide(num, den, out=score, where=den > 0)
    return Fused(g, _smooth(score, smooth_cells), maxw, spacing)


def _segments(score: np.ndarray, low: float, high: float) -> list[tuple[int, int]]:
    ok = np.nan_to_num(score, nan=-1.0) >= low
    d = np.diff(np.r_[False, ok, False].astype(int))
    return [(int(i), int(j)) for i, j in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1)
            if score[i:j + 1].max() >= high]  # valleys below `low` always split events


def _evidence(pairs: list[Pair], s: float, e: float, low: float) -> tuple[float, list[str], str]:
    """(raw max prob, evidence window ids, worst alignment) using result samples inside [s, e]."""
    pairs = sorted(pairs, key=lambda p: (p[0].window_id, p[0].sampling_profile))
    cands = []
    for w, r in pairs:
        pts, pr = np.asarray(r.sample_source_pts), np.asarray(r.probabilities)
        inside = (pts >= s - 1e-9) & (pts <= e + 1e-9)
        if inside.any():
            cands.append((w, r, float(pr[inside].max())))
    if not cands:  # event narrower than the sampling: use each covering window's nearest sample
        mid = (s + e) / 2
        for w, r in pairs:
            lo, hi = _span(r)
            if lo - 1e-9 <= mid <= hi + 1e-9:
                pts, pr = np.asarray(r.sample_source_pts), np.asarray(r.probabilities)
                cands.append((w, r, float(pr[np.argmin(np.abs(pts - mid))])))
    ev = [c for c in cands if c[2] >= low] or cands
    status = max((c[1].alignment_status for c in ev), key=_RANK.get, default="unknown")
    return (max((c[2] for c in cands), default=0.0),
            [c[0].window_id for c in cands if c[2] >= low], status)


def events_for_query(pairs: list[Pair], query: Query, *, duration: float, settings: Settings,
                     model_revision: str, config_hash: str) -> list[Event]:
    f, ex = settings.fusion, settings.export
    fz = fuse(pairs, duration=duration, grid_seconds=f.grid_seconds, smooth_cells=f.smooth_cells,
              edge_weight_floor=f.edge_weight_floor)
    step, n = f.grid_seconds, len(fz.grid)
    modal = unsupported_modality(query.text)
    events = []
    for i, j in _segments(fz.score, f.low, f.high):
        s, e = round(float(fz.grid[i]), 3), round(float(min(fz.grid[j], duration)), 3)
        if e - s < settings.coarse.min_candidate_seconds:
            continue
        reasons = []
        at_start, at_end = s <= step + 1e-9, duration - e <= step + 1e-9
        if at_start:
            reasons.append("touches_video_start")
        if at_end:
            reasons.append("touches_video_end")
        for idx, at_bound in ((i, at_start), (j, at_end)):
            if at_bound:
                continue
            if fz.max_weight[idx] < 0.5 and "boundary_near_window_edge" not in reasons:
                reasons.append("boundary_near_window_edge")
            if fz.spacing[idx] > f.sparse_spacing_sec and "sparse_sampling_boundary" not in reasons:
                reasons.append("sparse_sampling_boundary")
        if (i > 0 and np.isnan(fz.score[i - 1])) or (j + 1 < n and np.isnan(fz.score[j + 1])):
            reasons.append("adjacent_coverage_gap")
        if modal:
            reasons.append("unsupported_modality")
        raw_max, ids, status = _evidence(pairs, s, e, f.low)
        if raw_max < f.min_event_score:
            continue
        events.append(Event(
            event_id=stable_event_id(query.query_id, s, e, model_revision, config_hash),
            query_id=query.query_id, query=query.text, event_start_sec=s, event_end_sec=e,
            clip_start_sec=round(max(0.0, s - ex.pre_roll), 3), clip_end_sec=round(min(duration, e + ex.post_roll), 3),
            complete="unknown" if reasons else "likely", needs_review=bool(reasons), review_reasons=reasons,
            raw_score_max=round(raw_max, 4), alignment_status=status, evidence_window_ids=ids))
    return events
