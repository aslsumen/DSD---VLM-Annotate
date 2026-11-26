"""VideoJev-4B backend. torch/transformers are imported lazily; `to_result` is pure (no torch)."""
from __future__ import annotations

import gc
import hashlib
import json
import sys
import time

from ..models import AlignmentError, BackendOOM, GroundingResult, Window


def to_result(window: Window, query_id: str, model_id: str, record: dict, prediction: dict,
              extras: dict | None = None) -> GroundingResult:
    """Map VideoJev's clip-local record/prediction to global source seconds (alignment is "estimated":
    score_times lie on the requested sampling grid; each frame is the nearest decoded one)."""
    probs, times = prediction["probabilities"], record["score_times"]
    if len(probs) != len(times):
        raise AlignmentError(f"{window.window_id}/{query_id}: {len(probs)} probabilities vs {len(times)} score_times")
    o = window.clip_origin_sec
    interval = prediction.get("interval")
    cells = [(float(a), float(b)) for a, b in record["score_bounds"]]  # upstream: one (start, end) per score
    raw = {"interval": list(interval) if interval is not None else None,
           "score_bounds": [o + cells[0][0]] + [o + b for _, b in cells],  # contract: n+1 global cell edges
           "fps_actual": record["fps"], "frames": record["frames"], "grid_thw": list(record["grid_thw"]),
           "tokens": record["tokens"], "sampling_mode": record.get("sampling_mode"), **(extras or {})}
    return GroundingResult(
        window_id=window.window_id, query_id=query_id, model_id=model_id, probabilities=tuple(probs),
        sample_source_pts=tuple(o + t for t in times),
        predicted_local_interval=tuple(interval) if interval is not None else None,
        alignment_status="estimated", raw_response=raw)


class VideoJevBackend:
    needs_clip = True

    def __init__(self, model_path: str, model_id: str, model_revision: str, context_tokens: int = 8192,
                 device_map: str | dict = "auto", max_memory: dict | None = None,
                 attn_implementation: str = "flash_attention_2", threshold: float = 0.25,
                 feature_cache=None):
        self.model_path, self.model_id, self.model_revision = model_path, model_id, model_revision
        self.context_tokens, self.device_map = context_tokens, device_map
        self.max_memory = dict(max_memory) if max_memory else None  # own copy: accelerate rewrites values in place
        self.attn_implementation, self.threshold = attn_implementation, threshold
        self.feature_cache = feature_cache
        self._env = ""
        self._model = self._processor = self._prepare_video = None
        self._key = self._features = self._record = None  # last window's encoded features

    def load(self) -> None:
        if self._model is not None:  # the backend worker keeps the model loaded across jobs
            return
        import torch
        import transformers
        from transformers import AutoModel, AutoProcessor
        self._env = f"torch={torch.__version__} transformers={transformers.__version__}"
        self._processor = AutoProcessor.from_pretrained(self.model_path, revision=self.model_revision, trust_remote_code=True)
        kw = {"max_memory": dict(self.max_memory)} if self.max_memory else {}
        device_map = self.device_map
        if device_map == "auto" and self.max_memory:
            device_map = self._offload_map(torch)
        model = AutoModel.from_pretrained(
            self.model_path, revision=self.model_revision, trust_remote_code=True, dtype=torch.bfloat16,
            device_map=device_map,
            attn_implementation=self.attn_implementation, **kw)
        model.eval()
        model.prepare_for_inference()
        self._model = model
        # modeling_videojev does `from .processing_videojev import prepare_video`; reuse that exact function
        self._prepare_video = sys.modules[type(model).__module__].prepare_video

    def _offload_map(self, torch) -> dict:
        """CPU-offload device map with `head` pinned to GPU 0: CosineDecisionHead reads self.k.weight directly,
        bypassing accelerate's offload hook, so an offloaded head fails with 'Tensor on device meta'."""
        from accelerate import infer_auto_device_map, init_empty_weights
        from transformers import AutoConfig, AutoModel
        cfg = AutoConfig.from_pretrained(self.model_path, revision=self.model_revision, trust_remote_code=True)
        with init_empty_weights():
            m0 = AutoModel.from_config(cfg, trust_remote_code=True, dtype=torch.bfloat16)
        dmap = infer_auto_device_map(m0, max_memory=dict(self.max_memory), no_split_module_classes=m0._no_split_modules,
                                     dtype=torch.bfloat16)
        dmap = {k: v for k, v in dmap.items() if k.split(".")[0] != "head"}
        dmap["head"] = 0
        return dmap

    def _feature_key(self, window: Window) -> str:
        # Content key: the clip's bytes, so any change in source video, window bounds or cutter settings misses
        # automatically. It relies on a deterministic re-encode (libx264 output is the same for the same input,
        # args and thread count on one host); a non-deterministic cut only costs hits, never correctness.
        h = hashlib.sha256()
        with open(window.clip_path, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        h.update(json.dumps([1, window.fps, window.max_frames, self.context_tokens, self.model_id,  # 1 = key format version
                             self.model_revision, self.attn_implementation, self._env]).encode())
        return h.hexdigest()

    def _drop_cache(self) -> None:
        self._key = self._features = self._record = None

    def ground(self, window: Window, query_id: str, query: str) -> GroundingResult:
        import torch
        if self._model is None:
            raise RuntimeError("VideoJevBackend.load() has not been called")
        # The CUDA allocator has stats only after a CUDA model or tensor has initialized it.
        cuda = torch.cuda.is_initialized()
        key = self._feature_key(window)
        question = {"id": query_id, "task": "grounding", "query": query}
        try:
            if cuda:
                for i in range(torch.cuda.device_count()):
                    torch.cuda.reset_peak_memory_stats(i)
            t0 = time.perf_counter()
            with torch.inference_mode():  # same three steps as model.predict_video, features cached per window
                source = "memory"
                if key != self._key:
                    self._drop_cache()
                    hit = self.feature_cache.get(key) if self.feature_cache else None
                    if hit:
                        source = "disk"
                        features, record = hit["features"].to(hit["device"]), hit["record"]
                    else:
                        source = "encoded"
                        pixels, record = self._prepare_video(
                            self._processor, window.clip_path, fps=window.fps, max_frames=window.max_frames,
                            context=self.context_tokens)
                        features = self._model.encode_video(pixels, torch.tensor([record["grid_thw"]]))
                        if self.feature_cache:
                            self.feature_cache.put(key, features, record)
                    self._key, self._features, self._record = key, features, record
                prediction = self._model.predict_features(
                    self._processor, self._features, self._record, [question],
                    context=self.context_tokens, threshold=self.threshold)[0]
            extras = {"context_tokens": self.context_tokens, "feature_source": source,
                      "inference_ms": (time.perf_counter() - t0) * 1000,
                      "peak_vram_bytes": max(torch.cuda.max_memory_allocated(i)
                                             for i in range(torch.cuda.device_count())) if cuda else None}
        except torch.cuda.OutOfMemoryError as e:
            self._drop_cache()
            gc.collect()
            torch.cuda.empty_cache()
            raise BackendOOM(f"CUDA OOM on {window.window_id} ({window.max_frames} frames): {e}") from e
        return to_result(window, query_id, self.model_id, self._record, prediction, extras)

    def unload(self) -> None:
        self._drop_cache()
        self._model = self._processor = self._prepare_video = None
        gc.collect()
        if "torch" in sys.modules:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
