"""Sliding-window planning. Windows overlap and always cover [0, duration] without gaps."""
from __future__ import annotations


def plan_windows(duration_sec: float, window_seconds: float, stride_seconds: float) -> list[tuple[float, float]]:
    r = lambda x: round(x, 3)  # noqa: E731
    if duration_sec <= window_seconds:
        return [(0.0, r(duration_sec))]
    out, k = [], 0
    while k * stride_seconds + window_seconds < duration_sec:
        s = k * stride_seconds
        out.append((r(s), r(s + window_seconds)))
        k += 1
    last = (r(max(0.0, duration_sec - window_seconds)), r(duration_sec))
    if out[-1] != last:
        out.append(last)
    return out
