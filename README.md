# DSD — VLM Annotate

English | [简体中文](README.zh-CN.md)

A natural-language video event grounding and annotation backend. Given a video and event descriptions, it produces event timestamps, playable clips, and verification results. Human reviewers can accept, reject, or adjust events before compiling a dataset.

The implementation lives in [`video_grounding/`](video_grounding/). It exposes a Python CLI and an HTTP API for integration into a larger annotation system. This repository does not provide a complete business frontend, user authorization, or an object storage service.

## Current pipeline

```text
Video + prompts → probe → VideoJev coarse scan → candidate fusion → VideoJev refinement
                → Gemini verification (optional) → event and clip export
                → human review and boundary adjustment → reviewed dataset
```

- **VideoJev-4B** locates one or more event intervals. Supports multiple prompts, resumable jobs, and frame-count downgrades after GPU out-of-memory errors.
- **Gemini is integrated**, after refinement and before export. The current adapter uses the Decisions API with `gemini-decision-1`. Negative verdicts go into an audit list; candidates that could not be verified remain available for human review.
- **Human review** accepts, rejects, or adjusts event boundaries. Only reviewed events enter datasets.
- The standalone Qwen3-VL-4B verifier experiment is not part of the current pipeline; its model is not required. VideoJev's own processor and dependencies are still required.

## Documentation

| Document | Audience and contents |
|---|---|
| [Usage and deployment](video_grounding/docs/USAGE.md) | Installation, configuration, CLI, service operation, recovery, troubleshooting |
| [HTTP API integration](video_grounding/docs/API.md) | Requests, responses, states, errors, events, reviews, and datasets |
| [Internal engineering contracts](video_grounding/docs/CONTRACTS.md) | Time semantics, model adapter, fusion, persistence, and module interfaces |
| [Compatibility](video_grounding/docs/COMPATIBILITY.md) | Verified GPU/dependency combinations and platform issues |
| [Evaluation](video_grounding/docs/EVALUATION.md) | Test methods, dataset experiments, and quality limitations |
| [Performance](video_grounding/docs/PERFORMANCE.md) | Measured latency, memory use, and CPU offload |

The running service exposes request schemas at `/openapi.json` and interactive documentation at `/docs`. See [API.md](video_grounding/docs/API.md) for response fields and application semantics.

## Quick start

Run the following commands from the package directory:

```bash
cd video_grounding
```

1. Follow the [compatibility installation instructions](video_grounding/docs/COMPATIBILITY.md#install) to install GPU dependencies, matching FlashAttention/causal-conv1d, and ffmpeg/ffprobe.
2. Install service dependencies and configure the Gemini key:

   ```bash
   uv pip install -p .venv/bin/python -e '.[server,gemini]'
   cp .env.example .env
   # Edit .env and set GEMINI_API_KEY. Do not commit the key.
   ```

3. Create a machine-specific configuration:

   ```bash
   cp configs/rtx3070.yaml configs/local.yaml
   # Set model.local_path and runtime.max_memory for your machine.
   # Use default.yaml for a larger GPU; set verify.enabled: false to disable Gemini.
   ```

4. Run a job, or start the service:

   ```bash
   .venv/bin/video-grounding scan --video /data/demo.mp4 \
     --prompt 'A person opens a door' --config configs/local.yaml --out runs/demo

   .venv/bin/video-grounding serve --config configs/local.yaml \
     --jobs-root /data/grounding --media-root /data/videos \
     --host 127.0.0.1 --port 8800
   ```

Results are written to `runs/demo/events.json`, with exported clips under `clips/`. Use a separate directory for each new job; use `resume` to continue an existing one.

## Integrating into a complete system

The business backend submits a video path or HTTP(S) URL **accessible to the inference host** to `POST /v1/jobs`, stores the returned `job_id`, and polls its state. After completion, it retrieves events and clips, submits human reviews, and creates a dataset. Browsers must not depend on server-local file paths.

Each service process executes inference and dataset tasks serially. The surrounding system owns authentication, tenant isolation, uploads, URL access controls, request deduplication, notifications, and object storage. Deploy behind a controlled gateway or on a trusted network.

## Development checks

```bash
cd video_grounding
uv sync --group dev
uv run pytest
```

Tests cover synthetic/replay backends, time mapping, recovery, fusion, API behavior, and mocked Gemini verification. Passing them does not establish real GPU or live Gemini availability. See [Usage](video_grounding/docs/USAGE.md#validation-and-troubleshooting) for integration checks.
