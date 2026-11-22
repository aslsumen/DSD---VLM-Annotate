# Single video and single prompt performance

The speed KPI measures **one video × one prompt per backend job**. Report the actual seconds for that search
and its job RTF: processing seconds divided by that video's duration. Multi-prompt benchmark totals and their
per-prompt averages are excluded from product speed reporting.

## Product timing on 2026-11-22

Measured through the real API and worker on an RTX 3070 Laptop 8 GB, Ryzen 7 5800H, about 15 GB RAM available
to WSL, with CPU offload. The tested code was main base `a1b8279` plus the feature-cache changes at `02cdaf7`.
The model was VideoJev-4B revision `b614f1a6248ba1f169cd3bec9e4392758b566e5d`; inputs were 854×480 at 30 fps.
The low-VRAM config used a 6 GiB GPU / 9 GiB CPU weight budget, coarse 1 fps / 32 frames and refine 2 fps /
64 frames. Product verification and engine clip export were disabled; the backend processed preview clips.

Each value below is one completed **single-video, single-prompt** job. Both prompt-B runs reuse an already
loaded model. The comparison holds the video and prompt fixed, changing whether earlier visual features exist.

| Video | Duration | Prompt B, empty video cache | Same prompt B, reuse video cache | Time saved |
|---|---|---|---|---|
| YouCook2 `-AwyG1JcMp8` | 307.467 s | **178 s (job RTF 0.58)** | **97 s (job RTF 0.32)** | 45.5% |
| ROAD `2014-06-25-16-45-34_stereo_centre_02` | 394.5 s | **303 s (job RTF 0.77)** | **186 s (job RTF 0.47)** | 38.6% |

Prompt B is `place the dumplings above a pot of boiling water` for cooking and `the ego vehicle turns left`
for driving. Cached features were created by an earlier prompt A on the same uploaded video. New refinement
positions can still miss the cache. The empty-cache control deletes the video, verifies cache cleanup,
re-uploads the same file and runs B again while keeping the model loaded. B returns the same candidate times
and scores in both conditions: 2 cooking candidates and 10 driving candidates.

The preceding prompt-A searches were also single-prompt jobs:

| Video | Prompt A | Model state before job | Video cache before job | Processing time | Job RTF |
|---|---|---|---|---|---|
| Cooking | `place the filling on a wrapper and press the edges together` | Not loaded; this job includes loading | Empty | 231 s | 0.75 |
| Driving | `the ego vehicle is stopped` | Already loaded in the same worker | Empty | 322 s | 0.82 |

The worker stays alive across all six jobs, so only cooking A is a model cold start. An empty video cache does
not imply an unloaded model. Cache savings use the matched B runs: `(B_empty − B_reuse) / B_empty`; A and B
ask different questions and are not the cache-effect comparison.

## Measurement boundary and sample size

Processing time is `job.finished_at − job.started_at`, with one-second timestamp precision. It includes model
loading when it occurs in that job, inference, backend preview-extraction processing and result persistence.
It excludes upload transfer and queueing before the worker claims the job. Job RTF therefore differs from
pure engine RTF and from upload-to-candidates latency.

All six jobs succeeded. Each condition has **one observation**: no median, p90 or statistical speed guarantee
is inferred. This run checks candidate equivalence under cache reuse; it does not add a labelled quality
benchmark. The observed times apply to these 5–6.6 minute videos, this hardware and the tested cache code.

Evidence: [single_prompt_timing.json](../benchmarks/results/2026-11-22/single_prompt_timing.json) records prompt
text, model/cache state, durations, job times, candidate counts, source hashes and the original test log.

## Required protocol

Use one video and one prompt in every timed job. Record the exact prompt, video duration/resolution, code and
model revisions, config, GPU/VRAM, CPU/RAM, verification setting, model-loaded state and initial video-cache
state. Report model cold starts, model-warm/cache-empty searches and cache-reusing searches separately.

For a cache comparison, repeat the same video/prompt pair with the model already loaded in both conditions.
Report raw seconds and `time / video_duration` for each pair; do not divide multi-prompt job time by prompt
count. For repeated independent runs of a pair, report sample count, median and p90 separately for each state.
Failures and missing preview clips must be reported rather than silently counted as successful latency samples.

Full engine RTF measures the wall time of a single-prompt engine invocation, including loading when it occurs.
Upload-to-candidates latency starts after upload is complete and stored, and ends when that prompt's candidates
are persisted with previews available, or when a successful zero-candidate result is available. It includes
queueing and backend work; record upload transfer and any manual delay separately. Break stages down into
queueing, loading, coarse scan, refinement, optional verification, preview extraction and persistence when
instrumented. Neither full latency nor a complete stage breakdown was measured by this job-timestamp test.

Acceptance thresholds remain TBD. Representative 10–30 minute video/prompt pairs and a Gemini backend
comparison need their own single-prompt measurements. Quality and speed should be reported under the same
configuration; the multi-prompt quality runs do not provide product speed values.
