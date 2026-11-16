# Video grounding engine

English | [简体中文](README.zh-CN.md)

The zero-shot event grounding engine of VLM Annotate: given a video and event descriptions, it returns event intervals and clips. It is a library plus a debugging/evaluation CLI. In the product it runs inside the backend worker through `../backend/app/adapters/videojev.py` (one job = 1 video × 1 action; the backend cuts preview clips itself, so the adapter sets `export.cut_clips=false`). Queuing, human review and dataset export belong to the backend.

## Current pipeline

```text
Video + prompts → probe → VideoJev coarse scan → candidate fusion → VideoJev refinement
                → Gemini verification (optional) → event and clip export
```

- **VideoJev-4B** locates one or more event intervals. Supports multiple prompts, resumable jobs, and frame-count downgrades after GPU out-of-memory errors.
- **Gemini is integrated**, after refinement and before export. The current adapter uses the Decisions API with `gemini-decision-1`. Negative verdicts go into an audit list; candidates that could not be verified are kept and flagged for human review (done in the backend).
- The standalone Qwen3-VL-4B verifier experiment is not part of the current pipeline; its model is not required. VideoJev's own processor and dependencies are still required.

## Documentation

| Document | Audience and contents |
|---|---|
| [Usage and deployment](docs/USAGE.md) | Installation, configuration, CLI, recovery, troubleshooting |
| [Python API](docs/API.md) | `run_scan` / `resume` / `export`, progress callback, `events.json` fields |
| [Internal engineering contracts](docs/CONTRACTS.md) | Time semantics, model adapter, fusion, persistence, and module interfaces |
| [Compatibility](docs/COMPATIBILITY.md) | Verified GPU/dependency combinations and platform issues |
| [Evaluation](docs/EVALUATION.md) | Test methods, dataset experiments, and quality limitations |
| [Performance](docs/PERFORMANCE.md) | Measured latency, memory use, and CPU offload |

## Quick start

Run the following commands from the package directory:

```bash
cd video_grounding
```

1. Follow the [compatibility installation instructions](docs/COMPATIBILITY.md#install) to install GPU dependencies, matching FlashAttention/causal-conv1d, and ffmpeg/ffprobe.
2. Install the optional extras and configure the Gemini key:

   ```bash
   uv pip install -p .venv/bin/python -e '.[videojev,gemini]'
   cp .env.example .env
   # Edit .env and set GEMINI_API_KEY. Do not commit the key.
   ```

3. Create a machine-specific configuration:

   ```bash
   cp configs/rtx3070.yaml configs/local.yaml
   # Set model.local_path and runtime.max_memory for your machine.
   # Use default.yaml for a larger GPU; set verify.enabled: false to disable Gemini.
   ```

4. Run a job:

   ```bash
   .venv/bin/video-grounding scan --video /data/demo.mp4 \
     --prompt 'A person opens a door' --config configs/local.yaml --out runs/demo
   ```

Results are written to `runs/demo/events.json`, with exported clips under `clips/`. Use a separate directory for each new job; use `resume` to continue an existing one.

## Integrating into the product

The backend worker calls `run_scan` / `resume` from `video_grounding.scheduler` and passes `progress=` to update the job's progress; see [API.md](docs/API.md). The engine itself has no HTTP server, review UI or dataset builder.

## Development checks

```bash
cd video_grounding
uv sync --group dev
uv run pytest
```

Tests cover synthetic/replay backends, time mapping, recovery, fusion, progress reporting, and mocked Gemini verification. Passing them does not establish real GPU or live Gemini availability. See [Usage](docs/USAGE.md#validation-and-troubleshooting) for integration checks.
