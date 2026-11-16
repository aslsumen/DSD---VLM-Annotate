#!/usr/bin/env python
"""L1 GPU smoke: official predict_video vs VideoJevBackend.ground on one window, with RAM/VRAM logging.

Run on the GPU host:  python scripts/smoke_demo.py --model-path /models/VideoJev-4B --max-memory-gpu 6GiB
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DEMO_REPO, DEMO_FILE, DEMO_REV = "ZhuYuhan/VideoJev-Demo", "eating_spaghetti.mp4", "7e2b9685bca592c3b929268f6fcf82c4ad74b267"


def ram_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except ImportError:
        for line in open("/proc/self/status"):  # VmHWM = peak resident set
            if line.startswith("VmHWM"):
                return int(line.split()[1]) / 1024
    return float("nan")


def vram_mb(torch) -> dict:
    if not torch.cuda.is_available():
        return {}
    n = torch.cuda.device_count()
    return {"alloc": [round(torch.cuda.memory_allocated(i) / 2**20) for i in range(n)],
            "peak": [round(torch.cuda.max_memory_allocated(i) / 2**20) for i in range(n)]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--video", help="default: VideoJev-Demo eating_spaghetti.mp4 from the HF hub")
    ap.add_argument("--query", default="The woman in green eats pasta.")
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--max-frames", type=int, default=8)
    ap.add_argument("--context", type=int, default=8192)
    ap.add_argument("--device-map", default="auto")
    ap.add_argument("--max-memory-gpu", help="e.g. 6GiB, applied to every visible GPU")
    ap.add_argument("--max-memory-cpu", help="e.g. 32GiB")
    ap.add_argument("--attn", default="flash_attention_2")
    ap.add_argument("--repeat", type=int, default=0, help="extra uncached grounds to watch VRAM growth")
    args = ap.parse_args()

    import numpy as np
    import torch
    from video_grounding.adapters.videojev import VideoJevBackend
    from video_grounding.models import Window
    from video_grounding.probe import probe_video

    video = args.video
    if not video:
        from huggingface_hub import hf_hub_download
        video = hf_hub_download(DEMO_REPO, DEMO_FILE, repo_type="dataset", revision=DEMO_REV)
    max_memory = None
    if args.max_memory_gpu or args.max_memory_cpu:
        max_memory = {i: args.max_memory_gpu for i in range(torch.cuda.device_count())} if args.max_memory_gpu else {}
        if args.max_memory_cpu:
            max_memory["cpu"] = args.max_memory_cpu
    log: dict = {"video": video, "ram_mb": {}, "vram_mb": {}}

    def mark(tag: str) -> None:
        log["ram_mb"][tag], log["vram_mb"][tag] = round(ram_mb()), vram_mb(torch)
        print(f"[{tag}] RAM {log['ram_mb'][tag]} MB  VRAM {log['vram_mb'][tag]}", flush=True)

    backend = VideoJevBackend(args.model_path, "videojev-4b", "local", args.context,
                              args.device_map, max_memory, args.attn)
    mark("before_load")
    t0 = time.perf_counter()
    backend.load()
    log["load_s"] = round(time.perf_counter() - t0, 1)
    mark("after_load")

    question = {"id": "q", "task": "grounding", "query": args.query}
    official = backend._model.predict_video(backend._processor, video, [question], fps=args.fps,
                                            max_frames=args.max_frames, context=args.context,
                                            threshold=backend.threshold)[0]
    print("OFFICIAL", json.dumps(official), flush=True)
    mark("after_official")

    dur = probe_video(video).duration_sec
    window = Window("smoke", 0.0, dur, video, 0.0, fps=args.fps, max_frames=args.max_frames)
    result = backend.ground(window, "q", args.query)
    mark("after_adapter")
    same = bool(np.allclose(official["probabilities"], result.probabilities, rtol=1e-3, atol=1e-3))
    print("ADAPTER", json.dumps({"probabilities": result.probabilities, "pts": result.sample_source_pts,
                                 "interval": result.predicted_local_interval}), flush=True)
    assert same, "adapter probabilities differ from official predict_video"
    assert list(result.predicted_local_interval or ()) == list(official["interval"]), "interval differs"

    peaks = [result.raw_response["peak_vram_bytes"]]
    for i in range(args.repeat):
        backend._drop_cache()  # force re-encode so growth in the whole pipeline shows up
        peaks.append(backend.ground(window, "q", args.query).raw_response["peak_vram_bytes"])
        print(f"repeat {i + 1}: peak_vram_bytes={peaks[-1]}", flush=True)
    growth = bool(len(peaks) > 1 and peaks[0] and peaks[-1] > peaks[0] * 1.05)
    print("SMOKE_RESULT " + json.dumps({
        "ok": same, "adapter_matches_official": same, "frames": result.raw_response["frames"],
        "tokens": result.raw_response["tokens"], "inference_ms": result.raw_response["inference_ms"],
        "peak_vram_bytes": peaks, "vram_growth": growth, **log}))
    return 1 if growth else 0


if __name__ == "__main__":
    sys.exit(main())
