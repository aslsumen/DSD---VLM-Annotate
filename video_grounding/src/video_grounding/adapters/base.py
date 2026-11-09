"""Backend protocol plus the two GPU-free backends (synthetic for tests, replay for re-fusion)."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from ..models import BackendOOM, GroundingResult, Window
from ..settings import Settings


@runtime_checkable
class GroundingBackend(Protocol):
    model_id: str
    model_revision: str
    needs_clip: bool

    def load(self) -> None: ...
    def ground(self, window: Window, query_id: str, query: str) -> GroundingResult: ...
    def unload(self) -> None: ...


class SyntheticBackend:
    """Mimics VideoJev's sampling/pairing exactly (see docs/CONTRACTS.md) over scripted events."""

    needs_clip = False
    model_id = "synthetic"
    model_revision = "synthetic-v1"

    def __init__(self, events: dict[str, list[tuple[float, float]]] | None = None, *, peak: float = 0.8,
                 base: float = 0.05, noise: float = 0.02, seed: int = 0, oom_above_frames: int | None = None,
                 fail_plan: dict[str, int] | None = None):
        self.events = events or {}
        self.peak, self.base, self.noise, self.seed = peak, base, noise, seed
        self.oom_above_frames = oom_above_frames
        self._fails = dict(fail_plan or {})

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def ground(self, window: Window, query_id: str, query: str) -> GroundingResult:
        if self.oom_above_frames is not None and window.max_frames > self.oom_above_frames:
            raise BackendOOM(f"synthetic OOM at {window.max_frames} frames")
        if self._fails.get(window.window_id, 0) > 0:
            self._fails[window.window_id] -= 1
            raise RuntimeError(f"synthetic failure for {window.window_id}")
        dur = window.source_end_sec - window.source_start_sec
        fps = window.fps
        n = max(1, math.ceil(round(dur * fps, 6)))
        if n > window.max_frames:
            fps = window.max_frames / dur
            n = window.max_frames
        req = np.arange(n) / fps
        first = np.arange(0, n, 2)
        centers = (req[first] + req[np.minimum(first + 1, n - 1)]) / 2
        edges = np.r_[0.0, (centers[1:] + centers[:-1]) / 2, dur]
        pts = window.clip_origin_sec + centers
        member = np.zeros(len(pts))
        for s, e in self.events.get(query_id, []):
            dist = np.maximum(np.maximum(s - pts, pts - e), 0)
            member = np.maximum(member, np.clip(1 - dist, 0, 1))
        h = int.from_bytes(hashlib.sha1(f"{window.window_id}|{query_id}".encode()).digest()[:4], "big")
        noise = np.random.default_rng([self.seed, h]).uniform(-self.noise, self.noise, len(pts))
        probs = np.clip(self.base + (self.peak - self.base) * member + noise, 0, 1)
        k = int(np.argmax(probs))
        interval = (float(round(edges[k])), float(round(edges[k + 1])))
        raw = {"interval": list(interval), "score_bounds": (window.clip_origin_sec + edges).tolist(),
               "fps_actual": fps, "frames": n, "inference_ms": 0.0, "peak_vram_bytes": 0}
        return GroundingResult(window.window_id, query_id, self.model_id, tuple(probs.tolist()),
                               tuple(pts.tolist()), interval, "exact", raw)


class ReplayBackend:
    """Serves stored predictions from a window_predictions.jsonl; never calls a model."""

    needs_clip = False

    def __init__(self, path: str | Path):
        recs = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
        recs = [r for r in recs if r.get("status") == "succeeded"]
        if not recs:
            raise ValueError(f"{path}: no succeeded predictions to replay")
        self.model_id = recs[0].get("model_id", "replay")
        self.model_revision = recs[0]["model_revision"]
        self._by: dict[tuple[str, str], list[dict]] = {}
        for r in recs:
            self._by.setdefault((r["query_id"], r.get("sampling_profile", "coarse")), []).append(r)

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def ground(self, window: Window, query_id: str, query: str) -> GroundingResult:
        for r in self._by.get((query_id, window.sampling_profile), ()):
            if (abs(r["source_start_sec"] - window.source_start_sec) <= 1e-3
                    and abs(r["source_end_sec"] - window.source_end_sec) <= 1e-3):
                raw = {"interval": r.get("raw_interval"), "score_bounds": r.get("score_bounds"),
                       "fps_actual": r.get("fps_actual"), "resolution": r.get("resolution"),
                       "context_tokens": r.get("context_tokens"), "inference_ms": r.get("inference_ms"),
                       "peak_vram_bytes": r.get("peak_vram_bytes")}
                raw = {k: v for k, v in raw.items() if v is not None}
                iv = r.get("raw_interval")
                return GroundingResult(window.window_id, query_id, self.model_id, tuple(r["probabilities"]),
                                       tuple(r["sampled_pts"]), tuple(iv) if iv else None,
                                       r.get("alignment_status", "unknown"), raw)
        raise KeyError(f"no replay prediction for {query_id}/{window.sampling_profile}/"
                       f"{window.source_start_sec}-{window.source_end_sec}")


def make_backend(settings: Settings) -> GroundingBackend:
    rt = settings.runtime
    if rt.backend == "replay":
        if not rt.replay_path:
            raise ValueError("runtime.replay_path is required for the replay backend")
        return ReplayBackend(rt.replay_path)
    if rt.backend == "synthetic":
        return SyntheticBackend({})
    from .videojev import VideoJevBackend  # lazy: needs torch/transformers

    m = settings.model
    return VideoJevBackend(model_path=m.local_path or m.id, model_id=m.id, model_revision=m.revision,
                           context_tokens=settings.coarse.context_tokens, device_map=rt.device_map,
                           max_memory=rt.max_memory, attn_implementation=rt.attn_implementation,
                           threshold=settings.coarse.grounding_threshold)
