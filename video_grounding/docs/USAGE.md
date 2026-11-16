# Usage and deployment

English | [简体中文](USAGE.zh-CN.md)

This guide describes the current implementation. Run commands from `video_grounding/`. See [API.md](API.md) for the HTTP integration contract.

## Environment and installation

- Python ≥ 3.11; the verified GPU environment uses Python 3.12.
- `ffmpeg` and `ffprobe` must be on PATH for metadata inspection, window cutting, and clip export.
- VideoJev requires compatible CUDA/PyTorch, FlashAttention, and causal-conv1d. Follow the verified combination in [COMPATIBILITY.md](COMPATIBILITY.md); installing the base package alone is insufficient for real-model inference.
- Base dependencies are numpy, PyYAML, and Pydantic. Optional extras: `videojev`, `server`, and `gemini`.

After installing the GPU dependencies:

```bash
uv pip install -p .venv/bin/python -e '.[videojev,server,gemini]'
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

Use unique, nonempty query IDs and descriptions of visible events. Audio or intent cannot reliably be established from video frames alone. The CLI expects a local video; the HTTP service additionally supports URL download.

### 3. Resume and re-export

```bash
.venv/bin/video-grounding resume --job runs/demo
.venv/bin/video-grounding export --job runs/demo
# Adjust only fusion thresholds and re-export, without model inference.
.venv/bin/video-grounding export --job runs/demo --threshold 0.3 --low 0.2
```

`resume` checks the source fingerprint, model revision, and configuration hash. Changing configuration outside the `verify` section is rejected; create a new job directory instead. Preserve the source video at its original path. Successful predictions and cached verdicts are reused, although resume still loads the backend. `export` calls neither VideoJev nor Gemini; it regenerates outputs from stored predictions and verdicts.

To verify a completed job, stop any writers, enable `verify` in that job's `config.yaml`, configure the key, and run CLI `resume`. HTTP retry does not accept completed jobs.

**Cache limitation:** verdict keys include only query ID, clip start/end in microseconds, model name and a hash of the question text—not `verify.fps` or `max_height`. Changing sampling settings and resuming does not re-verify cached verdicts. Use a new job directory for sampling experiments; cache reuse is not a new evaluation.

### 4. Review, dataset creation, and evaluation

CLI `reviews.json` is an array; HTTP wraps the same items in a `reviews` object:

```json
[{"event_id":"evt_example","accepted":true,"start_sec":12.5,"end_sec":18.0}]
```

Replace the example event ID with an actual output ID. Times are source-video seconds.

```bash
.venv/bin/video-grounding review --job runs/demo --reviews reviews.json
.venv/bin/video-grounding dataset --jobs runs/demo --out datasets/demo --name demo
.venv/bin/video-grounding eval --pred runs/demo/events.json --reviews reviews.json
```

Alternatively, use `eval --gt gt.json`, with labels shaped as `{"events":[{"query_id":"open_door","start_sec":12.5,"end_sec":18.0}]}`. Review-based evaluation cannot measure missed-event recall; ground-truth evaluation supports temporal-IoU recall.

Datasets include only human-reviewed events. By default only accepted events are included; `--include-rejected` adds human-rejected events, not Gemini `rejected_events`. Adjusted boundaries cause clips to be recut from the source during dataset creation. Saving reviews does not rewrite original job events or clips.

## HTTP service deployment

```bash
.venv/bin/video-grounding serve --config configs/local.yaml \
  --jobs-root /data/grounding --media-root /data/videos \
  --host 127.0.0.1 --port 8800
```

- Use persistent storage and absolute paths for jobs, media, and models. The service account needs read access to media and write access to job directories.
- Each process has one model and one worker thread. Scans and dataset builds share a serial queue. Do not run multiple service processes against one jobs-root or modify active service jobs through the CLI.
- Startup recovers unfinished requests without `error.txt`. Failed jobs require explicit retry. Shutdown waits for the current task; allow sufficient termination time for long jobs.
- Health `ok` means the service responds, not that CUDA, model loading, or Gemini quota are available. Model loading is lazy.
- There is no built-in authentication, CORS configuration, tenant isolation, cancellation API, webhook/SSE, or idempotency key. The surrounding gateway/business service must implement these controls and notifications as needed.
- `--media-root` restricts local paths only. URL downloads do not enforce private-network filtering, file-size limits, or a business-domain allowlist. Validate URLs, redirects, and download resources at the integration boundary to prevent unauthorized access to internal resources.
- Gemini receives candidate video content. Both URL download and verification need outbound access; configure network and data-access policies accordingly.

## Outputs, retention, and cleanup

| File | Purpose |
|---|---|
| `job.sqlite`, `config.yaml` | Persistent recovery state and resolved configuration |
| `events.json` | Retained events, Gemini rejections, coverage gaps, model information |
| `window_predictions.jsonl` | Window predictions and actual sampling metadata |
| `clips/` | Playable event clips, when export is enabled |
| `manifest.json`, `metrics.json` | Provenance, versions, config hash, timings, downgrade counts |
| `windows/` | Rebuildable temporary window clips |
| `reviews.json` | Human decisions and adjusted times |

HTTP jobs also have `request.json`, `error.txt` on failure, and `source.mp4` for downloaded videos. Clean `windows/` only when no task is writing. Recovery and dataset recutting still require the source video. Do not delete the database to “retry.” There is no automatic retention policy or disk-cleanup API.

## Validation and troubleshooting

```bash
uv sync --group dev
uv run pytest
# Against an already running service; creates a job, submits sample reviews, and builds a dataset.
.venv/bin/python scripts/api_smoke.py --base http://127.0.0.1:8800 \
  --video /data/videos/demo.mp4 --prompt 'A person opens a door'
```

| Symptom | Check |
|---|---|
| Immediate failure due to a missing Gemini key | Check the service process environment/.env, or explicitly disable verify |
| completed with not_verified events | Check API errors, quota, and clip size; review manually or use CLI resume |
| scan_complete=false | Inspect coverage_gaps, permanent failures, and metrics; do not display “complete scan, no matches” |
| Empty results | Could mean no match, VideoJev filtering, or Gemini rejection; inspect rejected_events and coverage gaps |
| Clip endpoint returns 404 | Check export.cut_clips, Gemini rejection, and file presence |
| Resume configuration mismatch | Restore the original configuration or use a new job; do not force-edit the database |
| Slow processing or OOM | Check CPU offload, actual frame counts, and OOM counts; consult Performance |

Evaluation and compatibility documents record observations on specific environments, not guarantees for every video, device, or cloud API.
