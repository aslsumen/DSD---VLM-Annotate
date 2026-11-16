# Performance

Measured on the L1 host (see COMPATIBILITY.md): RTX 3070 Laptop 8 GB, config `configs/rtx3070.yaml`
(profile `dev_low_vram`, `max_memory {0: 6GiB, cpu: 9GiB}`: layers 0–18 on the GPU, 19–31 offloaded
to CPU). Sampling is the `default.yaml` setting: coarse 1 fps / 32 frames, refine 2 fps / 64 frames.
These numbers measure the offloaded 8 GB setup, not a reference GPU; CPU offload sets the speed, and a
16 GB+ GPU with `reference_gpu` (no offload) would remove it (not measured).

## Current: Charades-STA scan (2026-11-16)
300 videos, 822 queries, 2.5 h of video, 0 failed videos; `min_event_score` was 0.9 at the time of the
run and verify was on (method and results in [EVALUATION.md](EVALUATION.md)).

| Stage | Seconds per ~30 s video |
|---|---|
| Coarse scan | 8.8 |
| Refine | 9.2 |
| Gemini verify | 2.9 |
| Export | 1.3 |
| **Total** | **22.6 (1.3× real time)** |

The product adapter turns verify and clip export off, so its per-video time is the scan and refine
part only. A product-footage timing on this host is not measured yet (`scripts/smoke_videojev.py` is
pending). Going from the old sampling (0.5 fps / 16 frames coarse, 1 fps / 32 frames refine) to the
current one raised scan + refine from 14.8 s to 21.4 s per video on a 56-video subset (EVALUATION.md).

Memory: the VRAM figures below used 8 frames, so the current 32/64-frame calls need more; the OOM
ladder (`retry.oom_ladder`) lowers the frame count on out-of-memory. Peak VRAM at the current
settings is not recorded.

## Earlier measurements (2026-11-08, old sampling: 1 fps, 8 frames, context 8192)
Kept as a record of the first L1 run; do not use them for current speed.

Smoke (`scripts/smoke_demo.py`, 10 s demo): adapter probabilities match official `predict_video`
(allclose 1e-3); load 17 s; one ground 1.4 s (880 tokens); peak VRAM 6.7 GiB allocated; peak RSS 7.1 GB;
no VRAM growth across 2 repeated uncached grounds.

Full scan (70 s video, 3 queries, 9 coarse + 4 refine calls): 3:00 on the first run, 1:32 on a rerun
(weights in the OS file cache). First-query coarse 7–22 s per window, later queries on the same
window 1.6–2.7 s (cached features), refine 9–53 s. Peak VRAM 7.45 GiB allocated, peak RSS 7.1 GB, no
OOM downgrades.

- `ponytail:` refine windows are planned per query, so two queries hitting the same event cut and
  encode separate clips. Share refine windows across queries if multi-prompt scans get slow.
