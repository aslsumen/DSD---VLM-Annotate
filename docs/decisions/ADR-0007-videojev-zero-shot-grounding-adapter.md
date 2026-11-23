# ADR-0007 — VideoJev-4B zero-shot grounding engine as the first real adapter

- **Status:** Accepted (supersedes the "Alpha target" of [ADR-0004](ADR-0004-provisional-model-selection.md))
- **Date:** 2026-11-16
- **Evidence:** `video_grounding/docs/EVALUATION.md`; [MODEL_EVALUATION.md](../MODEL_EVALUATION.md)

## Context

ADR-0004 planned windowed Qwen2.5-VL as the first real detector. The team has since built and measured a
zero-shot temporal-grounding engine (`video_grounding/`, model VideoJev-4B) that returns a score curve and
event boundaries, and runs on an 8 GB laptop GPU with CPU offload.

Evidence (Charades-STA test subset, 300 videos / 822 queries, VideoJev-4B, before verification, default
`min_event_score` 0.5): recall 0.771, precision 0.737, R1@0.3/0.5/0.7 = 0.760/0.507/0.237, mIoU 0.486; scan +
refine took about 0.66× the video duration on an RTX 3070 Laptop 8 GB in that historical multi-query run; this is not a single-prompt product timing (current measurements: `video_grounding/docs/PERFORMANCE.md`). At the earlier default 0.9: recall 0.690,
R1@0.5 0.460. Below the SPEC targets either way (`video_grounding/docs/EVALUATION.md`).

*Note 2026-11-16 (later): this evidence is reference only. VideoJev was trained on Charades-STA, so these scores are
in-domain and do not support accuracy claims. It supports the integration and timing, not the accuracy. Main accuracy
benchmarks are now held-out sets (first small composites, `video_grounding/scripts/composite_bench.py`; since 2026-11-20 long videos, `video_grounding/scripts/heldout_bench.py`);
`min_event_score` 0.5 is provisional until re-checked there. The integration decision itself stands.*

*Note 2026-11-17 (superseded by the 2026-11-22 note below): held-out composite results (before verify): recall 0.573 pooled (driving 0.472, cooking 0.875)
vs the 0.85 target, CCR 0.78–0.94 vs 0.85, so the SPEC targets are not met; driving is weak and cooking floods the
reviewer with false candidates (`video_grounding/docs/EVALUATION.md`). `min_event_score` 0.5 is still not re-tuned
on them. The integration decision stands: human review stays mandatory and improvements are tracked in PB-71.*

*Note 2026-11-22: held-out long-video results (33 YouCook2 and 20 ROAD videos, verify off): recall 0.86 [0.81, 0.90]
cooking and 0.47 [0.39, 0.56] driving vs the 0.85 target, CCR 0.78 and 0.82 vs 0.85. Cooking recall meets the target
only as a point estimate. On driving, turns are found but lateral moves (0/24), overtakes and most stops are missed,
and absent prompts give almost as many candidates as present ones (8.4 vs 9.2). The decision stands under the same
conditions: human review mandatory, improvements in PB-71 (`video_grounding/docs/EVALUATION.md`).*

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
- **Gemini verification is always off** in the adapter (it overrides the engine YAML, like `cut_clips`): the human reviewer takes its place, and no footage leaves the machine.
- **Progress** is forwarded from the engine into the job's 0.05-0.35 progress band.
- Qwen2.5-VL remains a registered stub and can still be implemented behind the same boundary.
