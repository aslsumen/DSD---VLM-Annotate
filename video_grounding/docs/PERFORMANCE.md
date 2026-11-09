# Performance

Measured on the L1 host (see COMPATIBILITY.md), profile `dev_low_vram`: `max_memory {0: 6GiB, cpu: 9GiB}`,
which keeps layers 0–18 on the GPU and offloads layers 19–31 to CPU. These numbers measure the
offloaded dev setup, not a reference GPU.

## Smoke (`scripts/smoke_demo.py`, 10 s demo, 1 FPS, 8 frames, context 8192)
- Adapter probabilities match official `predict_video` (allclose 1e-3); identical interval.
- Load 17 s; one ground 1.4 s (880 tokens); peak VRAM 6.7 GiB allocated; peak RSS 7.1 GB.
- No VRAM growth across 2 repeated uncached grounds.

## Full scan (70 s video, 3 queries)
`video-grounding scan`: 9 coarse calls (3 windows × 3 queries) + 4 refine calls. Wall time including
model load: 3:00 on the first run, 1:32 on a rerun (model weights already in the OS file cache).

| Call | Time |
|---|---|
| Coarse, first query on a window (encode + predict) | 7–22 s |
| Coarse, later queries on the same window (cached features) | 1.6–2.7 s |
| Refine 18–30 s at 1 FPS | 9–53 s |

Peak VRAM 7.45 GiB allocated (8 GB card), peak RSS 7.1 GB, no OOM downgrades.

## Estimate for long videos on this host
A 20-minute video has 60 coarse windows: roughly 10–15 min per first query, plus about 2.5 min
for each extra query, plus refinement around candidates. Speed is set by CPU offload; a 16 GB+
GPU with `reference_gpu` (no offload) removes it.

- `ponytail:` refine windows are planned per query, so two queries hitting the same event cut and
  encode separate clips. Share refine windows across queries if multi-prompt scans get slow.
