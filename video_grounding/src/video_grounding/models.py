"""Shared data contracts. Every module and every agent codes against this file only.

Time convention: "global seconds" = source stream PTS seconds minus the video stream's
start_time, i.e. 0.0 is the first frame of the source video. Every *_sec field is global.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal


class AlignmentError(ValueError):
    """Model scores cannot be mapped to sample timestamps one-to-one."""


class BackendOOM(RuntimeError):
    """Backend ran out of (GPU) memory for this window; scheduler may retry with fewer frames."""


@dataclass(frozen=True)
class Query:
    query_id: str
    text: str


@dataclass(frozen=True)
class VideoInfo:
    path: str
    duration_sec: float
    fps: float              # avg_frame_rate
    time_base: str          # e.g. "1/15360"
    stream_index: int
    width: int              # display width (after rotation)
    height: int             # display height (after rotation)
    rotation: int           # degrees, 0/90/180/270
    has_audio: bool
    start_time_sec: float   # video stream start_time; global 0.0 == this source PTS
    is_vfr: bool
    fingerprint: str        # size + mtime + sha1 of head/tail bytes; resume rejects a changed source


@dataclass(frozen=True)
class Window:
    window_id: str
    source_start_sec: float
    source_end_sec: float
    clip_path: str          # "" when the backend does not need a clip file
    clip_origin_sec: float  # global time of the clip's first decoded frame (clip-local t=0)
    fps: float              # requested sampling fps
    max_frames: int         # requested frame cap (lowered by OOM downgrade)
    sampling_profile: str = "coarse"           # "coarse" | "refine"
    sampled_source_pts: tuple[float, ...] = ()  # filled only when known before inference


@dataclass(frozen=True)
class GroundingResult:
    window_id: str
    query_id: str
    model_id: str
    probabilities: tuple[float, ...]
    sample_source_pts: tuple[float, ...]  # global seconds, one per probability; never guessed from i/fps
    predicted_local_interval: tuple[float, float] | None  # model's own single interval, clip-local seconds
    alignment_status: Literal["exact", "estimated", "unknown"]
    raw_response: dict = field(default_factory=dict)
    # raw_response documented keys (all optional): interval, score_bounds (global cell edges,
    # len = len(probabilities)+1), fps_actual, frames, grid_thw, tokens, context_tokens,
    # resolution [w, h], inference_ms, peak_vram_bytes, timestamp_error_sec, sampling_mode

    def __post_init__(self):
        if len(self.probabilities) != len(self.sample_source_pts):
            raise AlignmentError(
                f"{self.window_id}/{self.query_id}: {len(self.probabilities)} probabilities "
                f"vs {len(self.sample_source_pts)} timestamps")
        if not self.probabilities:
            raise AlignmentError(f"{self.window_id}/{self.query_id}: empty probabilities")


@dataclass
class Event:
    event_id: str
    query_id: str
    query: str
    event_start_sec: float   # predicted event bounds
    event_end_sec: float
    clip_start_sec: float    # event bounds + pre/post roll, clamped to [0, duration]
    clip_end_sec: float
    complete: Literal["likely", "unknown"]
    needs_review: bool
    review_reasons: list[str]
    raw_score_max: float     # max raw window probability inside the event (uncalibrated sigmoid)
    alignment_status: str
    evidence_window_ids: list[str]
    clip_path: str | None = None


def stable_event_id(query_id: str, start_sec: float, end_sec: float,
                    model_revision: str, config_hash: str) -> str:
    key = f"{query_id}|{round(start_sec * 1000)}|{round(end_sec * 1000)}|{model_revision}|{config_hash}"
    return "evt_" + hashlib.sha1(key.encode()).hexdigest()[:12]
