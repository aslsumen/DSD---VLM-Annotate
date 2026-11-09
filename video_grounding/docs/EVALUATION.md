# Evaluation

## Gates
| Gate | What | Status |
|---|---|---|
| L0 | Pure algorithm, no GPU: `uv run --group dev pytest -q` | Passed: 41 tests, macOS (ffmpeg 8.0) and the L1 host (ffmpeg 4.4.2) |
| L1 | Real VideoJev inference, short video | Passed on RTX 3070 8 GB (CPU offload), see below |
| L2 | Small real set, human review, KPIs | Not run: needs labelled 10–30 min videos |
| L3 | 3070 low-VRAM adaptation | Works with offload; see PERFORMANCE.md for speed |

## L1 run (2026-11-08)
Video: 70 s, 1280×720 30 fps: VideoJev demo clip (10 s), 25 s test pattern, demo clip again, 25 s test pattern.
The demo clip shows the event at about 2–7.5 s (official model output).

| Query | Found events (s) | Expected (s) |
|---|---|---|
| `The woman in green eats pasta.` | 3.0–8.0, 37.5–44.0 | ~2–7.5, ~37–42.5 |
| `穿绿衣服的女人在吃意大利面` | 3.0–8.0, 36.0–44.5 | ~2–7.5, ~37–42.5 |
| `A dog runs across the street.` (negative) | none (max p 0.12) | none |

Every occurrence was found (2/2 per positive query), there were no false events, `scan_complete=true`,
and there were 0 coverage gaps. Boundaries are within one 2 s refine cell; the end of the second
occurrence overshoots by about 1.5–2 s, because the model still scores the demo clip's last seconds as positive.

## HTTP API run (2026-11-08)
`video-grounding serve` on the same host, then `scripts/api_smoke.py` (job → events → clip → reviews → dataset):
same 4 events as above; 96 s for the first job (model load included), 20 s for a second job with one prompt
(model stayed loaded); review metrics and a dataset with one adjusted, re-cut clip came back as expected;
a path outside `--media-root` was rejected with 400.

## Running KPIs
`video-grounding eval --pred <job>/events.json --gt gt.json` reports Event Recall/Precision,
R@IoU {0.3, 0.5, 0.7}, temporal mIoU and boundary error. Targets (SPEC): Event Recall ≥ 0.85,
R@IoU=0.5 ≥ 0.70, Complete Clip Rate ≥ 0.85 (human-judged; a clip still counts as complete if the
reviewed event extends at most 2 s past either end, `evaluate_review(..., tolerance_sec=2.0)`).

## L2: YouCook2 (2026-11-09, 游戏本, RTX 3070 Laptop 8 GB)
Labels `lmms-eval/YouCook2` (val), videos `lccshunli/youcook2-videos-only`. Not one of VideoJev's own
benchmarks. Three videos concatenated per batch; 4 steps per video = 12 prompts; every prompt searches the
whole video, so the other recipes act as distractors. A hit is IoU ≥ 0.3; complete = clip misses ≤ 2 s per end,
over hits.

Batch A (30.3 min), full pipeline, `fusion.min_event_score` 0 vs 0.9 (0.9 run reuses the same coarse pass):

| | recall | R@IoU0.5 | mIoU | complete | candidates/prompt | true step ranked 1st | refine | export |
|---|---|---|---|---|---|---|---|---|
| 0 | 11/12 | 0.92 | 0.70 | 9/11 | 22.8 | 8/12 | 604 windows, 139 min | 7.5 min |
| 0.9 | 12/12 | 0.92 | 0.73 | 12/12 | 8.8 | 9/12 | 289 windows, 78 min | 3.8 min |

Coarse pass 26 min (1092 window×prompt units), peak VRAM 7.44 GiB, no OOM, no failure. `kill -9` during
the coarse pass + `resume` continued from the last finished unit.

Batch B (25.4 min, holdout for the 0.9 threshold), coarse only: recall 11/12 at both 0 and 0.9 (0.95 loses one),
candidates/prompt 22.1 → 8.2, complete 10/11, but R@IoU0.5 only 0.33 and true step ranked 1st 6/12: short,
generic steps ("stir the food", "add onion paste") without refinement. Coarse pass 29 min (912 units).
