"""Timestamp and interval helpers.

Unit: seconds, relative to the *source video*, half-open interval ``[start, end)``.
"""

from __future__ import annotations

import math

#: Tolerance used when comparing a model-produced boundary to the video duration.
EPSILON_SECONDS = 1e-3


class InvalidIntervalError(ValueError):
    """Raised when an interval violates the timestamp contract."""


def round_seconds(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def validate_interval(start: float, end: float, duration: float | None) -> tuple[float, float]:
    """Return a normalised (start, end) or raise :class:`InvalidIntervalError`."""
    if not math.isfinite(start) or not math.isfinite(end):
        raise InvalidIntervalError("interval boundaries must be finite numbers")
    start = round_seconds(start)
    end = round_seconds(end)
    if start < 0:
        raise InvalidIntervalError("start must be >= 0")
    if end <= start:
        raise InvalidIntervalError("end must be greater than start")
    if duration is not None:
        limit = round_seconds(duration) + EPSILON_SECONDS
        if end > limit:
            raise InvalidIntervalError(
                f"interval end {end}s exceeds video duration {round_seconds(duration)}s"
            )
    return start, end


def clamp_to_duration(
    start: float, end: float, duration: float, min_duration: float = 0.25
) -> tuple[float, float]:
    """Clamp an interval into the source video, keeping a positive length."""
    start = max(0.0, min(round_seconds(start), round_seconds(duration) - min_duration))
    end = min(round_seconds(end), round_seconds(duration))
    if end - start < min_duration:
        end = min(round_seconds(duration), start + min_duration)
        start = max(0.0, end - min_duration)
    return round_seconds(start), round_seconds(end)


def preview_window(
    start: float, end: float, duration: float, padding: float, max_length: float
) -> tuple[float, float]:
    """Padded, clamped window used for the playable clip preview.

    Padding is applied symmetrically first; if the result exceeds ``max_length``
    it is truncated around the original interval.  The original candidate
    boundaries are never modified.
    """
    if max_length <= 0:
        raise InvalidIntervalError("max_length must be positive")
    candidate_length = end - start
    if candidate_length >= max_length:
        # Keep the window inside the candidate so the preview still shows it.
        return validate_interval(start, min(end, start + max_length), duration)
    budget = min(max_length, candidate_length + 2 * max(0.0, padding))
    pad = (budget - candidate_length) / 2.0
    p_start = max(0.0, start - pad)
    p_end = min(duration, end + pad)
    # Re-balance if clamping against a video edge shortened one side.
    missing = budget - (p_end - p_start)
    if missing > 0:
        if p_start <= 0:
            p_end = min(duration, p_end + missing)
        else:
            p_start = max(0.0, p_start - missing)
    return validate_interval(p_start, p_end, duration)


def format_seconds(value: float) -> str:
    """Human-readable ``HH:MM:SS.mmm`` (UI/debug helper)."""
    value = max(0.0, float(value))
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:06.3f}"
