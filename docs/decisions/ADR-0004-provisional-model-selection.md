# ADR-0004 — Provisional model choice: mock now, Qwen2.5-VL windowed for Alpha

- **Status:** Provisional / Supersedable
- **Date:** 2026-11-05
- **Deciders:** ML owner (role), Architect
- **Evidence:** [docs/MODEL_EVALUATION.md](../MODEL_EVALUATION.md) (cards fetched 2026-11-05)

## Context

The product needs **start/end seconds**, not a description. The dev laptop has an 8 GB RTX 4060. A 7–8 B model
in bf16 needs ~15–16 GB of weights and does not fit. Most video-VLM families have no temporal-grounding claim;
asking them for timestamps yields format hallucinations.

## Decision

1. **Sprint 2 MVP:** `MockTemporalAdapter` only, explicitly labelled in UI and export. No pretending.
2. **Alpha target:** Qwen2.5-VL, **windowed** (60 s windows, 10 s overlap, 16–32 frames, real fps passed to
   the processor), JSON-only output contract, deterministic decoding. 3B bf16 if the `qwen-research` licence
   is acceptable for the course; otherwise 7B on an external GPU / 4-bit with documented trade-off.
3. **Fallback:** SmolVLM2-2.2B (Apache-2.0, documented 5.2 GB video inference) as a **per-window presence
   classifier**; windows supply the time because the model has no grounding head.
4. Do **not** use InternVL3.x / LLaVA-Video / VideoLLaMA3 as timestamp sources.

## Why Qwen

The 7B card explicitly claims pinning down relevant video segments, mRoPE absolute-time alignment, and lists
`CharadesSTA/mIoU 43.6` — the only text-query localization benchmark found. It also documents that frame-rate
information is passed to the model to align absolute time, and warns that YaRN hurts temporal/spatial
localization (so we will not enable it).

## Consequences

- The adapter interface keeps this reversible; the registry entry is the only integration point.
- Licence choice is a release blocker to resolve before distributing weights (R-10).
- Real accuracy is **unmeasured**; the Alpha gate requires metrics, not claims.
- Windowing introduces merge heuristics and boundary drift; the evaluation protocol must measure it.

## Revisit trigger

Re-evaluate when: (a) 3B/4B grounding quality is measured, (b) Qwen3-VL grounding is independently verified,
(c) an external GPU becomes available, or (d) the licence blocks distribution.
