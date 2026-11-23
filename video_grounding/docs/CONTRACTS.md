# Contracts

Source of truth for data types: `src/video_grounding/models.py`. This file pins module
signatures, the VideoJev output semantics we verified, and the job-directory layout.
Public integration contract: [API.md](API.md). Setup, CLI and operations: [USAGE.md](USAGE.md).
Historical spec name: `SPEC_ZeroShot_Video_Event_Grounding_MVP_v1.1` (not included in this checkout).

## Time
- Global seconds: source video-stream PTS minus stream `start_time`; 0.0 = first frame.
- A window clip is a re-encoded file cut from the source. `Window.clip_origin_sec` is the global
  time of the clip's first decoded frame; VideoJev reports clip-local times relative to that
  frame, so `global = clip_origin_sec + local`.

## VideoJev-4B semantics (read from HF code, revision `b614f1a6248ba1f169cd3bec9e4392758b566e5d`)
- `predict_video(processor, path, questions, fps, max_frames, context, threshold)` =
  `prepare_video` -> `encode_video` -> `predict_features`. The `record` (score times) is NOT
  returned by `predict_video`, so the adapter calls the three steps itself.
- `prepare_video(processor, path, *, fps, max_frames, context) -> (pixel_values, record)`,
  `record = {frames, fps, grid_thw, tokens, score_times, score_bounds, sampled_duration}`.
- Sampling: requested grid `arange(ceil(dur*fps))/fps` relative to the first decoded frame's PTS;
  if that exceeds `max_frames`, uniform `effective_fps = max_frames/dur` over the clip. Each
  requested time takes the nearest decoded frame; `score_times` use the *requested* grid, so the
  mapping is `alignment_status="estimated"`, error <= half a source frame interval.
- Temporal patch 2: one probability per frame **pair**; `len(probabilities) == ceil(frames/2)
  == len(score_times)`; `score_times[k]` = mean of the pair's times; upstream `score_bounds` is an
  `(n, 2)` array of per-cell `[start, end]` (edges at midpoints between pairs, outer edges 0 and
  sampled_duration). `GroundingResult.raw_response["score_bounds"]` stores the `n + 1` global edges.
- `probabilities` = sigmoid of a cosine head (uncalibrated). `interval` = single max-likelihood
  segment, rounded to whole seconds, **always non-empty** -> never use it to decide "event
  present"; never treat it as "all events". Decoder defaults: threshold 0.25, smooth 1.
- Resolution: chosen inside `prepare_video` (per-frame cap 640*640 px, tokens <= context*4/5).
  We only pre-scale window clips to <= 720p height; no other resolution knob exists.
- Load: `AutoModel.from_pretrained(path, trust_remote_code=True, dtype=torch.bfloat16,
  device_map=..., attn_implementation="flash_attention_2")` then `model.prepare_for_inference()`
  (casts visual tower + head to FP32).
- CPU offload (`device_map: auto` + `max_memory`): the adapter builds the map itself and pins
  `head` to GPU 0. `CosineDecisionHead` reads `self.k.weight` directly, which bypasses
  accelerate's offload hook, so an offloaded head fails with "Tensor on device meta".

## Fusion
- Each result is interpolated onto the 0.5 s global grid inside its `score_bounds` span.
- Where results with different `fps_actual` overlap, only the densest sampling counts: coarse
  windows find events, and refine windows alone set the score and boundaries inside their span.
- Results of equal density are averaged with an edge-distance weight (1 at the window centre,
  floor 0.05 at an inner window edge). A window edge that lies on the video start or end truncates
  nothing, so it is not treated as an edge. `max_weight < 0.5` at an event boundary sets
  `boundary_near_window_edge`.
- Events whose `raw_score_max` is below `fusion.min_event_score` (default 0.5, provisional: chosen on Charades-STA for VideoJev-4B, checked on the held-out long-video benchmark, which keeps 3.5 candidates per absent cooking prompt and 8.4 per absent driving prompt, see EVALUATION.md)
  are dropped before refinement and export. events.json lists each query's events by descending
  `raw_score_max`, so reviewers see the likely ones first.

## Verify (Stage V, `verifier.py`)
- Runs after refine and before export when `verify.enabled` (on in `default.yaml` and `rtx3070.yaml`;
  the class default is off). Each event's clip span (`clip_start_sec..clip_end_sec`) is cut at
  `verify.max_height` (default 480) and resampled to `verify.fps` (default 2.0), then sent inline to the Gemini
  Decisions API (`verify.model`, default `gemini-decision-1`, endpoint `v1beta/decisions`) as one yes/no question
  built from the query text (`_INSTRUCTIONS` plus true/false `_CRITERIA`: a proposed clip, informal query text, the event
  may be brief or at the clip edge). The model scores it in one forward pass, with no generated text, and returns a calibrated
  `P(true)`. The verdict is `{present: p_present >= 0.5, p_present, model}`. A 429 response is retried for about 4 minutes
  to wait out per-minute limits.
- Key: `GEMINI_API_KEY` env var or `video_grounding/.env` (template `.env.example`, gitignored).
  A missing key fails the job before scanning starts. Install with `uv sync --extra gemini`.
- Verdicts are cached in the `verdicts` table, keyed by `(query_id, clip_start_us, clip_end_us, model, QUESTION_ID)`;
  `QUESTION_ID` hashes the question text, so editing it re-verifies.
  Resume reuses cached verdicts and calls the API only for missing ones; `export` never calls the API.
  Sampling settings (`verify.fps`, `max_height`) are not in the cache key: use a new job for sampling comparisons. `verify` is excluded from `config_hash`, so
  changing it never blocks a resume or changes event ids. To verify a finished job, enable `verify`
  in its `config.yaml` and resume the job.
- Gemini only removes refined events: `present=false` moves the event from `events` to
  `rejected_events` in events.json (audit trail, no clip cut). `verdict` holds the Gemini result.
  A call that fails after the SDK retries (5xx, per-minute 429), or a clip over 20 MB, keeps the event
  with `verdict: null`, `needs_review` and `not_verified`; a resume retries it. A 429 that outlasts the
  retries (daily quota) stops the stage, so the remaining events stay `not_verified` until a later resume.

## Module responsibilities and signatures

Media and model adapter:
- `probe.probe_video(path: str) -> VideoInfo` (ffprobe JSON; rotation from side_data/tags;
  VFR = r_frame_rate != avg_frame_rate or irregular frame durations).
- `cutter.cut_window_clip(src: str, start_sec: float, end_sec: float, out_path: str,
  info: VideoInfo, max_height: int = 720) -> float` - video-only re-encode (fast), honours
  rotation, temp file + atomic rename, returns `clip_origin_sec` (global time of the clip's
  first frame, measured, not assumed).
- `cutter.export_event_clip(src: str, clip_start_sec: float, clip_end_sec: float, out_path: str,
  info: VideoInfo, crf: int = 20, preset: str = "fast") -> None` - libx264 + aac (or no audio
  when `info.has_audio` is False), temp + atomic rename, never touches `src`.
- `adapters/videojev.VideoJevBackend(model_path: str, model_id: str, model_revision: str,
  context_tokens: int = 8192, device_map: str | dict = "auto", max_memory: dict | None = None,
  attn_implementation: str = "flash_attention_2", threshold: float = 0.25)` implementing the
  protocol below. Caches the last window's encoded features so several queries on one window
  encode once. Converts CUDA OOM into `BackendOOM` after freeing tensors.

Scheduling and data pipeline:
- `adapters/base.py`: `GroundingBackend` Protocol (`model_id: str`, `model_revision: str`,
  `needs_clip: bool`, `load()`, `ground(window, query_id, query) -> GroundingResult`, `unload()`),
  `SyntheticBackend`, `ReplayBackend`, `make_backend(settings) -> GroundingBackend`
  (imports `adapters.videojev` lazily).
- `sampler.plan_windows(duration_sec, window_seconds, stride_seconds) -> list[tuple[float, float]]`.
- `fusion.py`, `refinement.py`, `settings.py`, `persistence.py`, `scheduler.py`,
  `evaluation.py`, `cli.py`, `configs/*.yaml`.

## Job directory (`--out`)
```
job.sqlite                 # jobs / windows / predictions / events / artifacts / verdicts (source of truth)
config.yaml                # resolved settings snapshot; config_hash = sha256 of canonical JSON of the resolved settings minus `verify` (settings.config_hash)
windows/                   # temp window clip, deleted once the window is grounded
window_predictions.jsonl   # regenerated from SQLite; SPEC 8.2 fields
events.json                # SPEC 8.1 schema + coverage_gaps + per-query warnings
clips/<event_id>.mp4
manifest.json              # versions, model revision, config hash, video fingerprint, timings
metrics.json               # window counts, failures, OOMs, peak VRAM, durations
```
- Window key: `(job_id, query_id, window_start_us, window_end_us, sampling_profile, model_revision)`.
- Event id: `models.stable_event_id(query_id, start, end, model_revision, config_hash)`.

## Integration

The Python API (`run_scan`, `resume`, `export`, progress callback) is documented in [API.md](API.md); [USAGE.md](USAGE.md) covers the CLI.
A completed job may still have coverage gaps or unverified candidates. Callers must inspect
`scan_complete`, `coverage_gaps`, `verdict` and `review_reasons` separately.

## Model revision caveat

The configured revision is used for identity, event IDs and resume checks. The current VideoJev adapter
loads `local_path` or model ID without passing an explicit `revision` to `from_pretrained`.
For reproducibility, deploy a pre-downloaded snapshot at the declared revision through `model.local_path`.
