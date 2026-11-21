# Performance

Measured on the L1 host (see COMPATIBILITY.md): RTX 3070 Laptop 8 GB, config `configs/rtx3070.yaml`
(profile `dev_low_vram`, `max_memory {0: 6GiB, cpu: 9GiB}`: layers 0–18 on the GPU, 19–31 offloaded
to CPU). Sampling is the `default.yaml` setting: coarse 1 fps / 32 frames, refine 2 fps / 64 frames.
These numbers measure the offloaded 8 GB setup, not a reference GPU; CPU offload sets the speed, and a
16 GB+ GPU with `reference_gpu` (no offload) would remove it (not measured).

## Current: Charades-STA scan (2026-11-16, reference set)
300 videos, 822 queries (2.7 per video), 2.5 h of video, 0 failed videos, `min_event_score` 0.5,
verify on (method and results in [EVALUATION.md](EVALUATION.md)).

| Stage | Seconds per ~30 s video |
|---|---|
| Coarse scan | 8.9 |
| Refine | 10.9 |
| Gemini verify | 3.8 |
| Export | 1.5 |
| **Total** | **25.0 (about 0.84× the video duration)** |

The product adapter turns verify and clip export off, so its per-video time is the scan and refine
part only: 19.8 s, about 0.66× the video duration. Videos longer than Charades' ~30 s are not
measured; coarse windows grow linearly with length, refine with the number of kept events. At
`min_event_score` 0.9 the same run took 22.6 s (refine 9.2 s, fewer events kept). Product-style timing on
5–7 min videos is in the next section. Going from the old sampling (0.5 fps / 16 frames coarse, 1 fps / 32 frames refine) to the
current one raised scan + refine from 14.8 s to 21.4 s per video on a 56-video subset (EVALUATION.md).

Memory: the VRAM figures below used 8 frames, so the current 32/64-frame calls need more; the OOM
ladder (`retry.oom_ladder`) lowers the frame count on out-of-memory. Peak VRAM at the current
settings is not recorded.

## Product timing and the feature cache (2026-11-21)

Host: RTX 3070 Laptop 8 GB with about 3 GB of weights offloaded to CPU (`configs/rtx3070.yaml`, a
correctness profile, not target hardware). Measured through the backend (API + worker, videojev adapter)
with `scripts/smoke_videojev.py`: one action per job, as the product runs it. Time is the job's
start-to-finish wall time; RTF = that time ÷ video duration. The first job of each row also loads the
model, so compare the two prompt-B columns.

| Video | Length | Prompt A, empty cache | Prompt B, warm cache | Prompt B, empty cache | Saved by the cache |
|---|---|---|---|---|---|
| YouCook2 `-AwyG1JcMp8` | 307 s | 195 s (0.64×) | 95 s (0.31×) | 201 s (0.65×) | 53% |
| ROAD `2014-06-25-16-45-34_stereo_centre_02` | 394.5 s | 504 s (1.28×) | 223 s (0.57×) | 390 s (0.99×) | 43% |

The feature cache (`feature_cache` in USAGE.md) stores each window's visual features on the worker's
disk, so a later prompt on the same video skips decoding and visual encoding. What a warm cache still
pays for is per-prompt scoring, clip cutting, and refine tiles at positions no earlier prompt used.
Results do not change: an 8-prompt scan of `-AwyG1JcMp8` with an empty and then a warm cache gave
probabilities identical to the old code on all 180 window predictions and the same 28 events (scan
wall time 897 s empty, 664 s warm). That scan's 65 entries (15 coarse windows and 50 refine
tiles) took 1.9 GB of cache, about 29 MB per entry.

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
