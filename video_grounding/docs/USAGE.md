# Usage and deployment

English | [简体中文](USAGE.zh-CN.md)

This guide describes the current implementation. Run commands from `video_grounding/`. See [API.md](API.md) for the Python API used by the backend adapter.

## Environment and installation

- Python ≥ 3.11; the verified GPU environment uses Python 3.12.
- `ffmpeg` and `ffprobe` must be on PATH for metadata inspection, window cutting, and clip export.
- VideoJev requires compatible CUDA/PyTorch, FlashAttention, and causal-conv1d. Follow the verified combination in [COMPATIBILITY.md](COMPATIBILITY.md); installing the base package alone is insufficient for real-model inference.
- Base dependencies are numpy, PyYAML, and Pydantic. Optional extras: `videojev` and `gemini`.

After installing the GPU dependencies:

```bash
uv pip install -p .venv/bin/python -e '.[videojev,gemini]'
ffmpeg -version
ffprobe -version
.venv/bin/video-grounding --help
```

A subsequent `uv sync` may resolve PyTorch again. Preserve and check the validated CUDA wheel combination when maintaining a GPU host.

## Model, API key, and local configuration

Copy `configs/default.yaml` for a larger GPU, or `configs/rtx3070.yaml` for low-VRAM CPU offload. Set model paths and memory budgets for the actual host.

```yaml
# Merge into the corresponding sections; do not duplicate YAML section names.
model:
  id: ZhuYuhan/VideoJev-4B
  revision: b614f1a6248ba1f169cd3bec9e4392758b566e5d
  local_path: /models/VideoJev-4B
verify:
  enabled: true
  model: gemini-decision-1
  fps: 2.0
  max_height: 480
```

Without `local_path`, the adapter loads by model ID and may download files on first use. Prepare a complete local model for offline deployment. Loading uses `trust_remote_code=True`. The adapter currently does **not** pass the configured revision explicitly to `from_pretrained`: revision participates in identity and recovery checks, but alone does not pin Hub downloads. For reproducibility, download the declared revision in advance, point `local_path` at that snapshot, and keep the configured revision consistent with it.

Gemini is already integrated after refinement. Install the `gemini` extra and provide `GEMINI_API_KEY` through the process environment or `.env`. Lookup order is: environment variable, current-directory `.env`, then the package's project-root `.env`. For wheel installations, explicitly inject the environment variable rather than relying on source-directory layout. The key is not written to job configuration or outputs.

The supplied `default.yaml` and `rtx3070.yaml` enable verification; bare `Settings()` without a configuration defaults to verification disabled. Set `verify.enabled: false` explicitly for offline operation or to omit verification. An arbitrary Gemini chat model is not interchangeable with the configured model: this adapter calls the Decisions API.

## Configuration and frame sampling

YAML overrides only the specified fields; omitted fields use `settings.py` defaults. Unknown fields are rejected.

| Stage | Parameter | Default / meaning |
|---|---|---|
| Coarse | `coarse.window_seconds` / `stride_seconds` | 30 / 20 seconds |
| Coarse | `coarse.fps` / `max_frames` | 1.0 / 32 |
| Refine | `refine.enabled` | true |
| Refine | `refine.fps` / `max_frames` / `window_seconds` | 2.0 / 64 / 30 seconds |
| Refine | `expand_min_seconds` / `max_span_seconds` | 5 / 180 seconds |
| Fusion | `fusion.high` / `low` | 0.25 / 0.15, hysteresis thresholds |
| Candidate filtering | `fusion.min_event_score` | 0.5, applied before refinement and at export |
| Gemini | `verify.fps` / `max_height` | 2 frames/second / 480 pixels high |
| Export | `export.cut_clips` | true; disabling it still produces event JSON |
| Export | `pre_roll` / `post_roll` | 0.5 seconds each |
| Retry | `retry.max_attempts` / `oom_ladder` | 3 / [48, 32, 24, 16, 12, 8, 4] |
| Feature cache | `feature_cache.dir` / `max_gb` | `~/.cache/video_grounding/features` / 50; encoded window features are reused by later prompts on the same video (least recently used entries are deleted above the cap); `dir: null` disables it. The product adapter instead puts it under the backend data dir, one subdirectory per video (`engine/features/video-<id>`, removed with the video), with the same global cap. Results are identical with or without it |

VideoJev frame counts depend on window duration, fps, and max_frames. When the requested count exceeds the cap, effective sampling density is reduced uniformly over the clip. To increase density, check both fps and the frame cap; keep window duration and stride unchanged for a density comparison. OOM recovery can still reduce frames: inspect `metrics.json` (`oom_downgrades`) and actual sampling metadata in `window_predictions.jsonl`. Denser sampling does not guarantee better accuracy.

Gemini receives the event clip including pre/post-roll, not the coarse windows. `verify.fps` controls both local clip resampling and the API video-processing parameter. There is no Qwen-style `max_frames` setting. Clips exceeding the local 20 MiB check are not sent; the event remains with `not_verified`.

## CLI workflow

### 1. Preflight

```bash
.venv/bin/video-grounding probe --video /data/demo.mp4 \
  --config configs/local.yaml --prompt 'A person opens a door'
```

`probe` loads the backend and grounds up to the first 10 seconds. It is not just an ffprobe call and does not run Gemini verification.

### 2. Scan

Single prompt:

```bash
.venv/bin/video-grounding scan --video /data/demo.mp4 \
  --config configs/local.yaml --prompt 'A person opens a door' --out runs/demo
```

For multiple prompts, create `prompts.json`:

```json
[
  {"query_id": "open_door", "text": "A person opens a door"},
  {"query_id": "sit_down", "text": "A person sits down"}
]
```

```bash
.venv/bin/video-grounding scan --video /data/demo.mp4 \
  --config configs/local.yaml --prompt-file prompts.json --out runs/multi
```

Use unique, nonempty query IDs and descriptions of visible events. Audio or intent cannot reliably be established from video frames alone. The CLI expects a local video.

### 3. Resume and re-export

```bash
.venv/bin/video-grounding resume --job runs/demo
.venv/bin/video-grounding export --job runs/demo
# Adjust only fusion thresholds and re-export, without model inference.
.venv/bin/video-grounding export --job runs/demo --threshold 0.3 --low 0.2
```

`resume` checks the source fingerprint, model revision, and configuration hash. Changing configuration outside the `verify` section is rejected; create a new job directory instead. Preserve the source video at its original path. Successful predictions and cached verdicts are reused, although resume still loads the backend. `export` calls neither VideoJev nor Gemini; it regenerates outputs from stored predictions and verdicts.

To verify a completed job, stop any writers, enable `verify` in that job's `config.yaml`, configure the key, and run CLI `resume`.

**Cache limitation:** verdict keys include only query ID, clip start/end in microseconds, model name and a hash of the question text—not `verify.fps` or `max_height`. Changing sampling settings and resuming does not re-verify cached verdicts. Use a new job directory for sampling experiments; cache reuse is not a new evaluation.

### 4. Evaluation

```bash
.venv/bin/video-grounding eval --pred runs/demo/events.json --gt gt.json
```

Ground-truth labels are shaped as `{"events":[{"query_id":"open_door","start_sec":12.5,"end_sec":18.0}]}`; times are source-video seconds. `eval` reports temporal-IoU recall.

Accuracy benchmarks live in `scripts/`: `composite_bench.py` (held-out YouCook2 and BDD-X composites, the main accuracy check) and `charades_sta.py` (reference only: VideoJev was trained on Charades-STA). Methods and results: [EVALUATION.md](EVALUATION.md).

## Outputs, retention, and cleanup

| File | Purpose |
|---|---|
| `job.sqlite`, `config.yaml` | Persistent recovery state and resolved configuration |
| `events.json` | Retained events, Gemini rejections, coverage gaps, model information |
| `window_predictions.jsonl` | Window predictions and actual sampling metadata |
| `clips/` | Playable event clips, when export is enabled |
| `manifest.json`, `metrics.json` | Provenance, versions, config hash, timings, downgrade counts |
| `windows/` | Temporary window clip; each is deleted once its window is grounded |

Recovery (`resume`) still requires the source video. Do not delete the database to “retry.” There is no automatic retention policy.

## Validation and troubleshooting

```bash
uv sync --group dev
uv run pytest
```

| Symptom | Check |
|---|---|
| Immediate failure due to a missing Gemini key | Check the process environment/.env, or explicitly disable verify |
| completed with not_verified events | Check API errors, quota, and clip size; review manually or use CLI resume |
| scan_complete=false | Inspect coverage_gaps, permanent failures, and metrics; do not display “complete scan, no matches” |
| Empty results | Could mean no match, VideoJev filtering, or Gemini rejection; inspect rejected_events and coverage gaps |
| No clip file for an event | Check export.cut_clips, Gemini rejection, and file presence |
| Resume configuration mismatch | Restore the original configuration or use a new job; do not force-edit the database |
| Slow processing or OOM | Check CPU offload, actual frame counts, and OOM counts; consult Performance |

Evaluation and compatibility documents record observations on specific environments, not guarantees for every video, device, or cloud API.
