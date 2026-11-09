"""Stage B (local refinement) and Stage C (boundary expansion) span planning.

Stage D (completeness re-query with expanded prompts) and Stage E (cross-event consolidation) are
deferred: completeness here is only a review flag from fusion, never a verified claim.
Pure planning; the scheduler grounds the returned windows and re-fuses.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Event
from .sampler import plan_windows
from .settings import Coarse, Refine


@dataclass
class Span:
    start: float
    end: float
    exp_l: float  # current expansion on each side; doubled each time Stage C extends that side
    exp_r: float


def _merge(spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for sp in sorted(spans, key=lambda s: s.start):
        if out and sp.start <= out[-1].end:
            if sp.end > out[-1].end:
                out[-1].end, out[-1].exp_r = sp.end, sp.exp_r
        else:
            out.append(sp)
    return out


def tile(start: float, end: float, window_seconds: float) -> list[tuple[float, float]]:
    if end - start <= 1e-6:
        return []
    return [(round(start + a, 3), round(start + b, 3))
            for a, b in plan_windows(end - start, window_seconds, window_seconds * 2 / 3)]


def plan_spans(events: list[Event], duration: float, *, coarse: Coarse, refine: Refine) -> list[Span]:
    exp = max(refine.expand_min_seconds, coarse.window_seconds - coarse.stride_seconds)
    return _merge([Span(max(0.0, e.event_start_sec - exp), min(duration, e.event_end_sec + exp), exp, exp)
                   for e in events])


def extend_spans(spans: list[Span], events: list[Event], duration: float, *, refine: Refine,
                 grid_seconds: float) -> tuple[list[tuple[float, float]], list[Span]]:
    """Stage C: grow spans whose events touch a non-video edge. Returns (new tiles, merged spans)."""
    new: list[tuple[float, float]] = []
    eps = grid_seconds + 1e-9
    for sp in spans:
        budget = refine.max_span_seconds - (sp.end - sp.start)
        if budget <= 0:
            continue
        hits = [e for e in events if e.event_end_sec > sp.start and e.event_start_sec < sp.end]
        if sp.start > 0 and any(e.event_start_sec - sp.start <= eps for e in hits):
            add = min(sp.exp_l, sp.start, budget)
            new += tile(sp.start - add, sp.start, refine.window_seconds)
            sp.start, sp.exp_l, budget = sp.start - add, sp.exp_l * 2, budget - add
        if sp.end < duration and budget > 0 and any(sp.end - e.event_end_sec <= eps for e in hits):
            add = min(sp.exp_r, duration - sp.end, budget)
            new += tile(sp.end, sp.end + add, refine.window_seconds)
            sp.end, sp.exp_r = sp.end + add, sp.exp_r * 2
    return new, _merge(spans)
