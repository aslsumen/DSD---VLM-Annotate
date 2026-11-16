# Evaluation

## Gates
| Gate | What | Status |
|---|---|---|
| L0 | Pure algorithm, no GPU, no API: `uv run --group dev pytest -q` | Passed: 44 tests, macOS (ffmpeg 8.0) |
| L1 | Real VideoJev inference, short video | Passed on RTX 3070 8 GB (CPU offload), see below |
| L2 | Benchmark KPIs on held-out composites (`youcook2_a`, `youcook2_b`, `bddx`) | Running since 2026-11-16, results pending; the SPEC target check is made here |
| L2-ref | Charades-STA reference (in-domain: VideoJev trained on it) | Ran 300 videos; reference only, see below |
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

## Running KPIs
`video-grounding eval --pred <job>/events.json --gt gt.json` reports Event Recall/Precision,
R@IoU {0.3, 0.5, 0.7}, temporal mIoU and boundary error. Targets (SPEC, docs/REQUIREMENTS.md §6): Event Recall ≥ 0.85
(found = IoU ≥ 0.3), Complete Clip Rate ≥ 0.85 (human-judged; a clip still counts as complete if the
reviewed event extends at most 2 s past either end, `evaluate_review(..., tolerance_sec=2.0)`). Reviewers correct spans, so strict-overlap numbers (R@IoU 0.5/0.7, mIoU, R1)
are diagnostics with no target (R@IoU=0.5 ≥ 0.70 was dropped 2026-11-16).

## L2: Held-out composite benchmarks (main accuracy check)
VideoJev was trained on Charades-STA, so its Charades scores are in-domain and say little about accuracy on new
footage. The main accuracy benchmarks are therefore three held-out composites built by `scripts/composite_bench.py`;
each joins several long source videos into one composite (854×480, 30 fps) and every prompt searches the whole
composite, so a prompt can match several times and the other videos act as distractors.

| Benchmark | Composite | Prompts | Ground truth |
|---|---|---|---|
| `youcook2_a`, `youcook2_b` | 3 long YouCook2 val cooking videos each | 12 labelled steps + 6 "absent" prompts (cooking steps from other recipes that never happen in the composite; 3 easy, unlike anything shown, and 3 hard, looking close) | One GT span per labelled step |
| `bddx` | 20 BDD100K dashcam clips, about 40 s each | 7 driving prompts (turn left/right, lane change, stop for red light / lead vehicle / pedestrian, go on green) + 1 absent prompt (collision) | 72 GT spans from BDD-X segments, same-prompt segments less than 1 s apart merged |

```
python scripts/composite_bench.py prep NAME DIR     # NAME: youcook2_a | youcook2_b | bddx; needs curl and ffmpeg (bddx also remotezip)
video-grounding scan --video DIR/video.mp4 --prompt-file DIR/prompts.json --config configs/rtx3070.yaml --out DIR/run
python scripts/composite_bench.py score DIR         # KPIs as JSON
```

`score` reports event recall and precision at IoU ≥ 0.3, R@IoU 0.5 / 0.7, mIoU, Complete Clip Rate with an oracle
reviewer, events per prompt, events on absent prompts, a per-prompt breakdown, all before and after Gemini verify, and
Gemini as a classifier (true events kept, false events removed). R1 is not used, because a prompt can have several GT
spans. The SPEC targets (recall 0.85, CCR 0.85) are checked on these sets; events on absent prompts are reported.

### Results
Running (started 2026-11-16 on the RTX 3070 laptop, `configs/rtx3070.yaml`, current defaults), filled in when done.
Until then no held-out number exists, and the SPEC target check is pending. `fusion.min_event_score` 0.5 was chosen on
Charades (below) and is provisional: re-check it on these composites, which contain absent prompts. It has not been
changed yet.

## Reference: Charades-STA (in-domain)
Charades-STA is kept only as a reference next to the VideoJev paper numbers, not as the KPI, the target check or the
basis for tuning: the model was trained on it. Labels are the `test` split of HF `lmms-lab/charades_sta` (3720 queries over
1334 indoor videos, ~30 s each; 4-fold zipped Charades 480p videos from the same repo). `scripts/charades_sta.py`
takes a seed-0 shuffle of the test videos, runs every query of a video through scan → refine → verify with
one loaded model, and scores all finished videos:

```
python scripts/charades_sta.py run   DATA_DIR N configs/rtx3070.yaml   # reruns skip finished videos
python scripts/charades_sta.py score DATA_DIR > kpis.json
```

It reports the engine KPIs (recall, precision, R@IoU, mIoU, boundary error over all events, before and after
verify), the standard Charades-STA R1@{0.3,0.5,0.7} and mIoU on the top-scoring event per query, Complete Clip
Rate with an oracle reviewer (accepts events matched at IoU ≥ 0.3, adjusts them to GT), a verify threshold
sweep, a split by GT length and the per-stage time.

### Results (2026-11-16)
游戏本, RTX 3070 Laptop 8 GB, `configs/rtx3070.yaml` (CPU offload), VideoJev-4B `b614f1a`, current sampling
(coarse 1 fps / 32 frames, refine 2 fps / 64 frames), `min_event_score` 0.9 (the default then; now 0.5, see
below), current Gemini question. 300 videos, 822 queries, 2.5 h of
video, 0 failed videos, 0 unverified events.

| | Event recall | Precision | R1@0.3 | R1@0.5 | R1@0.7 | R1 mIoU | Queries with no event | CCR (oracle) |
|---|---|---|---|---|---|---|---|---|
| Before verify | 0.690 | 0.768 | 0.683 | 0.460 | 0.215 | 0.437 | 12.3% | 0.778 |
| After verify (p ≥ 0.5) | 0.593 | 0.784 | 0.589 | 0.397 | 0.191 | 0.378 | 25.3% | 0.772 |
| After verify (p ≥ 0.3) | 0.663 | 0.776 | 0.657 | 0.440 | 0.204 | 0.420 | 15.7% | 0.778 |

Below the targets on this in-domain set (recall 0.85, CCR 0.85); the target check proper is made on the held-out composites (pending).

- **Verify on Charades:** Gemini kept 487/567 true events (86%) and removed 37/171 false ones (22%), so it costs
  recall for +1.6 points of precision. Every Charades query happens in its video, so a "false" event (IoU < 0.3
  with GT) can still show the action; Gemini said yes to 134 of the 171. A yes/no question about the clip cannot
  fix a misplaced span. Verify earns its cost only when prompts can be absent from the video (cooking data, A/B
  above).
- **By GT length (before verify):** recall 0.42 for spans < 5 s (83 queries, 23% of them get no event), 0.68 for
  5–10 s (542), 0.83 for ≥ 10 s (197). Short actions are the main loss.
- **Time:** 22.6 s per ~30 s video (scan 8.8, refine 9.2, verify 2.9, export 1.3), about 0.75× the video
  duration. Videos average 2.7 queries each.

Old vs current sampling defaults on the same 56 videos (before verify, so the Gemini question plays no part):

| Defaults | Event recall | R1@0.5 | R1@0.7 | R1 mIoU | Queries with no event | Scan + refine |
|---|---|---|---|---|---|---|
| Coarse 0.5 fps / 16, refine 1 fps / 32 | 0.598 | 0.425 | 0.230 | 0.409 | 21.3% | 14.8 s |
| Coarse 1 fps / 32, refine 2 fps / 64 | 0.672 | 0.431 | 0.178 | 0.427 | 10.9% | 21.4 s |

Denser sampling finds more events (fewer queries left empty) but does not tighten boundaries. After verify, with
the old and new question respectively, recall went from 0.420 to 0.552 on these 56 videos.

**Paper reference (not comparable as is):** VideoJev-4B reports R1@0.3/0.5/0.7 82.8/69.4/40.3, mIoU 60.1 on
Charades. That run uses TimeLens-refined labels (ours are the original ones), feeds the whole video at 4 fps up to
640×640 with a 262144-token context (ours: 30 s windows, 8192 tokens) and always returns one span per query (ours
leaves 12% of queries empty at `min_event_score` 0.9 and 1% at 0.5, scored as IoU 0). A model-only run under the paper protocol would separate the
model's ceiling from the pipeline's losses; it has not been run.

### Short spans and `min_event_score` (2026-11-16)
Chosen on Charades only, so the 0.5 default is provisional until the held-out composites (with absent prompts) confirm it.
The 103 queries whose GT span (clipped to the video) is under 5 s, at `min_event_score` 0.9: 49 hit (IoU ≥ 0.3).
Of the 54 misses, 25 have an event overlapping GT but too wide (median 18 s against a median GT of 4.5 s), 14 were
found by the model and then dropped by `min_event_score`, 7 sit elsewhere, 8 have no usable signal in GT.

Re-fusing the stored predictions of the 300-video run (no model calls; queries that the 0.9 filter left without
refinement are scored on coarse samples only, so lower thresholds are, if anything, underestimated):

| Fusion variant | Recall | Precision | R1@0.5 | R1 mIoU | No event | < 5 s recall | < 5 s R1@0.5 |
|---|---|---|---|---|---|---|---|
| `min_event_score` 0.9 | 0.690 | 0.768 | 0.465 | 0.444 | 12.3% | 0.476 | 0.369 |
| `min_event_score` 0.5 (new default) | 0.771 | 0.738 | 0.513 | 0.494 | 0.9% | 0.592 | 0.427 |
| 0.5, segment threshold 0.5 (`low` = `high`) | 0.659 | 0.630 | 0.364 | 0.411 | 2.3% | 0.563 | 0.262 |
| 0.5, segments trimmed to ≥ 50% of their peak | 0.691 | 0.637 | 0.384 | 0.425 | 0.9% | 0.602 | 0.301 |

Narrowing segments in fusion makes every length bin worse: wide events come from the model scoring a long stretch
high, which fusion cannot undo. Tightening short spans needs denser model input (not yet tested). Charades has no
absent prompts, so the cost of 0.5 on prompts that never happen (the case 0.9 was set for on cooking data) is
unmeasured here.

### Validation run at `min_event_score` 0.5 (2026-11-16)
The same 300 videos, 822 queries and config as the results above, rerun with the new default 0.5 (every kept event
refined). 0 failed videos; 1 event unverified (Gemini refused the clip with `prohibited_content`).

| | Event recall | Precision | R1@0.3 | R1@0.5 | R1@0.7 | R1 mIoU | Queries with no event | CCR (oracle) |
|---|---|---|---|---|---|---|---|---|
| Before verify | 0.771 | 0.737 | 0.760 | 0.507 | 0.237 | 0.486 | 1.1% | 0.786 |
| After verify (p ≥ 0.5) | 0.629 | 0.777 | 0.625 | 0.419 | 0.198 | 0.399 | 20.6% | 0.774 |
| After verify (p ≥ 0.3) | 0.726 | 0.763 | 0.719 | 0.479 | 0.220 | 0.458 | 7.3% | 0.784 |

- The re-fusion estimate held (recall 0.771, precision 0.738, R1@0.5 0.513). Against 0.9 (before verify): recall
  +8.1 points, R1@0.5 +4.7, CCR +0.8, precision −3.1, queries with no event 12.3% → 1.1%. All three SPEC targets
  are still missed on this in-domain set.
- **By GT length (before verify):** recall 0.58 for spans < 5 s (83 queries; 0.42 at 0.9), 0.77 for 5–10 s
  (542; 0.68), 0.86 for ≥ 10 s (197; 0.83). Precision on < 5 s spans is 0.57.
- **Verify:** Gemini kept 517/634 true events (82%) and removed 78/225 false ones (35%): −14.2 points of recall
  for +4.0 of precision. Same conclusion as at 0.9.
- **Time:** 25.0 s per ~30 s video (scan 8.9, refine 10.9, verify 3.8, export 1.5). Scan + refine alone, what
  the product adapter runs, is 19.8 s, about 0.66× the video duration. Refine grows with the extra kept events.

### Gemini question A/B (2026-11-16)
Clips from the first 56 videos (old sampling defaults), each sent to `gemini-decision-1` with both questions:
123 events covering ≥ 50% of a GT span (positives); 81 same-caption clips of the same length placed ≥ 1 s away from
the GT span (wrong time); 49 positive clips paired with a caption from another video that shares no content word
with any caption of this video (absent). Present = p ≥ 0.5.

| Question | Positives kept | Wrong-time removed | Absent removed | AUC wrong-time | AUC absent |
|---|---|---|---|---|---|
| `Does the following event visibly happen in this video clip?` | 71.5% | 97.5% | 93.9% | 0.972 | 0.952 |
| Current (`verifier.py` `_INSTRUCTIONS` + `_CRITERIA`) | 84.6% | 96.3% | 93.9% | 0.981 | 0.963 |

The bare question wrongly rejected mostly with p in 0.3–0.49 on short, dark clips of simple actions ("person
opens a cabinet"). The new question says the clip is a proposal, the text is informal and the event may be brief
or at the clip edge. It keeps more true events and separates better (higher AUC), not only a looser cutoff.
