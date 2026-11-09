# Compatibility

## Verified host (L1, 2026-11-08)
RTX 3070 Laptop 8 GB, driver 546.30, WSL2 Ubuntu (kernel 5.15), 15 GB RAM + 4 GB swap, ffmpeg 4.4.2.

| Package | Version |
|---|---|
| Python | 3.12.12 |
| torch / torchvision | 2.8.0+cu128 / 0.23.0+cu128 (cu128 runs on driver 546.30) |
| transformers | 5.14.1 (pinned by the model) |
| accelerate | 1.15.0 |
| av | 18.1.0 |
| flash-linear-attention, fla-core | 0.4.2 |
| flash-attn | 2.8.3.post2 (prebuilt wheel `cu12torch2.8cxx11abiTRUE-cp312`) |
| causal-conv1d | 1.7.0 (prebuilt wheel, same tags) |

Model: `ZhuYuhan/VideoJev-4B` @ `b614f1a6248ba1f169cd3bec9e4392758b566e5d` (8.4 GB, 2 shards).

## Install
```bash
uv venv -p 3.12 .venv
uv pip install -p .venv/bin/python torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install -p .venv/bin/python -e '.[videojev]'
# flash-attn / causal-conv1d: install the matching prebuilt wheels from their GitHub releases with
# --no-deps (building from source needs nvcc matching torch's CUDA).
```

## Known issues
- **torchvision missing upstream.** The model's install list omits it, but `Qwen3VLVideoProcessor`
  requires it. It is in our `videojev` extra.
- **CPU offload breaks the head.** With `device_map="auto"` and a GPU memory cap, accelerate puts
  `head` on CPU and inference fails with `Tensor on device meta is not on the expected device`.
  `VideoJevBackend` builds the device map itself and pins `head` to GPU 0.
- **Rotation sign depends on the muxer.** ffmpeg 4.4 writes `-metadata:s:v rotate=270` as a 90°
  clockwise matrix. `probe` reads the display matrix, so it reports what players will show.
- **ffmpeg < 5.1** has no `-fps_mode`; the cutter falls back to `-vsync 0`.
