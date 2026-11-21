"""Typed settings. One YAML file -> Settings; config_hash(settings) pins a job's configuration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Runtime(_Section):
    profile: Literal["dev_low_vram", "reference_gpu", "replay"] = "reference_gpu"
    backend: Literal["videojev", "replay", "synthetic"] = "videojev"
    device_map: str | dict = "auto"
    max_memory: dict[int | str, str] | None = None
    attn_implementation: str = "flash_attention_2"
    replay_path: str | None = None


class ModelCfg(_Section):
    id: str = "ZhuYuhan/VideoJev-4B"
    revision: str = "b614f1a6248ba1f169cd3bec9e4392758b566e5d"
    local_path: str | None = None


class Coarse(_Section):
    window_seconds: float = 30
    stride_seconds: float = 20
    fps: float = 1.0
    max_frames: int = 32
    grounding_threshold: float = 0.25
    context_tokens: int = 8192
    min_candidate_seconds: float = 0.5


class Refine(_Section):
    enabled: bool = True
    fps: float = 2.0
    max_frames: int = 64
    window_seconds: float = 30
    expand_min_seconds: float = 5
    max_span_seconds: float = 180


class Verify(_Section):
    """Stage V: Gemini confirms each event clip after refine. Needs GEMINI_API_KEY (see verifier.py)."""
    enabled: bool = False
    model: str = "gemini-decision-1"
    fps: float = 2.0
    max_height: int = 480


class Fusion(_Section):
    grid_seconds: float = 0.5
    smooth_cells: int = 3
    high: float = 0.25
    low: float = 0.15
    edge_weight_floor: float = 0.05
    sparse_spacing_sec: float = 1.5  # VideoJev: 1 score per frame pair → 1 s cells @2 FPS (refine), 2 s @1 FPS (coarse)
    # drop events whose raw_score_max is lower (before refine and export); chosen on Charades-STA with VideoJev-4B
    # (docs/EVALUATION.md Charades sweep); provisional: Charades is in-domain for VideoJev, so re-check on the held-out
    # composites (scripts/composite_bench.py), and again when the model or sampling changes
    min_event_score: float = 0.5


class Export(_Section):
    cut_clips: bool = True
    pre_roll: float = 0.5
    post_roll: float = 0.5
    crf: int = 20
    preset: str = "fast"


class Retry(_Section):
    max_attempts: int = 3
    oom_ladder: list[int] = [48, 32, 24, 16, 12, 8, 4]


class FeatureCacheCfg(_Section):
    dir: str | None = "~/.cache/video_grounding/features"  # None disables the cache
    max_gb: float = 50.0


class Settings(_Section):
    runtime: Runtime = Runtime()
    model: ModelCfg = ModelCfg()
    coarse: Coarse = Coarse()
    refine: Refine = Refine()
    verify: Verify = Verify()
    fusion: Fusion = Fusion()
    export: Export = Export()
    retry: Retry = Retry()
    feature_cache: FeatureCacheCfg = FeatureCacheCfg()


def load_settings(path: str | Path) -> Settings:
    return Settings.model_validate(yaml.safe_load(Path(path).read_text()) or {})


def dump_settings(s: Settings) -> str:
    return yaml.safe_dump(s.model_dump(), sort_keys=False)


def config_hash(s: Settings) -> str:
    # mode="json" stringifies dict keys, so {0: "6GiB", "cpu": ..} sorts without a TypeError
    # verify only adds verdicts on top of events: changing it must not block resume or change event ids
    # feature_cache never changes results, so it must not block resume or change event ids either
    canon = json.dumps(s.model_dump(mode="json", exclude={"verify", "feature_cache"}), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()
