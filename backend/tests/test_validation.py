"""Timestamp contract tests."""

from __future__ import annotations

import pytest
from app.validation import (
    InvalidIntervalError,
    clamp_to_duration,
    format_seconds,
    preview_window,
    validate_interval,
)


def test_validate_interval_accepts_half_open_interval_inside_video() -> None:
    start, end = validate_interval(10.0, 20.5, duration=60.0)
    assert (start, end) == (10.0, 20.5)


def test_validate_interval_rejects_negative_start() -> None:
    with pytest.raises(InvalidIntervalError):
        validate_interval(-0.1, 5.0, 60.0)


def test_validate_interval_rejects_zero_length() -> None:
    with pytest.raises(InvalidIntervalError):
        validate_interval(5.0, 5.0, 60.0)


def test_validate_interval_rejects_end_past_duration() -> None:
    with pytest.raises(InvalidIntervalError):
        validate_interval(10.0, 61.0, 60.0)


def test_validate_interval_allows_end_equal_to_duration() -> None:
    assert validate_interval(50.0, 60.0, 60.0) == (50.0, 60.0)


def test_validate_interval_rejects_non_finite() -> None:
    with pytest.raises(InvalidIntervalError):
        validate_interval(float("nan"), 10.0, 60.0)


def test_preview_window_pads_and_clamps_to_video() -> None:
    start, end = preview_window(1.0, 3.0, duration=60.0, padding=1.0, max_length=90.0)
    assert start == 0.0
    assert end == 4.0


def test_preview_window_never_exceeds_video_end() -> None:
    start, end = preview_window(58.0, 59.5, duration=60.0, padding=2.0, max_length=90.0)
    assert start < end
    assert end <= 60.0


def test_preview_window_respects_max_length() -> None:
    start, end = preview_window(100.0, 160.0, duration=600.0, padding=5.0, max_length=30.0)
    assert end - start <= 30.0
    assert start >= 100.0


def test_preview_window_keeps_original_boundaries_untouched() -> None:
    original = (10.0, 12.0)
    preview_window(*original, duration=60.0, padding=3.0, max_length=90.0)
    assert original == (10.0, 12.0)


def test_clamp_to_duration_keeps_positive_length() -> None:
    start, end = clamp_to_duration(59.99, 60.0, duration=60.0, min_duration=1.0)
    assert 0 <= start < end <= 60.0
    assert end - start >= 1.0


def test_format_seconds() -> None:
    assert format_seconds(3725.5) == "01:02:05.500"
