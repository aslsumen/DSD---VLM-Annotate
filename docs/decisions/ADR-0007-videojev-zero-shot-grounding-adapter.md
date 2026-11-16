# ADR-0007 — VideoJev-4B zero-shot grounding engine as the first real adapter

- **Status:** Accepted (supersedes the "Alpha target" of [ADR-0004](ADR-0004-provisional-model-selection.md))
- **Date:** 2026-11-16
- **Evidence:** `video_grounding/docs/EVALUATION.md`; [MODEL_EVALUATION.md](../MODEL_EVALUATION.md)

## Context

ADR-0004 planned windowed Qwen2.5-VL as the first real detector. The team has since built and measured a
zero-shot temporal-grounding engine (`video_grounding/`, model VideoJev-4B) that returns a score curve and
event boundaries, and runs on an 8 GB laptop GPU with CPU offload.

Evidence (Charades-STA test subset, 300 videos / 822 queries, VideoJev-4B, before verification): recall 0.690,
precision 0.768, R1@0.3/0.5/0.7 = 0.683/0.460/0.215, mIoU 0.437, about 1.3x video duration of processing time
on an RTX 3070 Laptop 8 GB. These numbers use `min_event_score` 0.9; a re-run with the new default 0.5 is in
progress (offline estimate: recall 0.771).

## Decision

Plug the engine into the existing job queue as the `videojev` adapter (`backend/app/adapters/videojev.py`).
The adapter boundary, the DB-backed queue and the single worker (ADR-0001) are unchanged. One job is still
1 video x 1 action; a batch endpoint (`POST /projects/{id}/actions/{id}/jobs`) fans out one job per video.

## Consequences

- **Exhaustive adapters.** The adapter sets `exhaustive = True`. The pipeline then keeps every event (no
  `max_candidates_per_job` truncation, ordered by score descending so likely events come first) and treats
  zero events as success ("the action does not occur"), not as a retryable failure. Other adapters are unchanged.
- **Resume on retry.** Each job gets a stable engine work directory
  `<data_dir>/storage/engine/job-<job_id>/`. A retried attempt resumes from the engine's SQLite state; if the
  engine config, model revision or video changed it discards the directory and rescans.
- **Model loaded once per worker process** (module-level cache); evicted and unloaded after an engine failure.
- **Install split.** The worker venv needs `pip install -e ./video_grounding[videojev]` (Python 3.12, CUDA torch).
  The API process does not need it: `is_available()` only checks that `VLM_VIDEOJEV_CONFIG` (if set) exists, because the
  API calls it at enqueue time. A worker without the engine fails the job with `ADAPTER_UNAVAILABLE` (not retryable).
- **Configuration.** `VLM_VLM_ADAPTER=videojev` selects it by default; `VLM_VIDEOJEV_CONFIG` points at an engine
  YAML file (unset = engine defaults). The engine's own clip cutting is disabled; the backend cuts previews.
- **Gemini verification stays off by default** (engine setting), so no footage leaves the machine.
- **Progress** is forwarded from the engine into the job's 0.05-0.35 progress band.
- Qwen2.5-VL remains a registered stub and can still be implemented behind the same boundary.
