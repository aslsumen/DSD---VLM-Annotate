# ADR-0002 — Timestamp and interval contract

- **Status:** Accepted (normative)
- **Date:** 2026-11-05
- **Deciders:** Architect, Backend, Frontend, ML

## Context

Temporal annotation fails silently when time units, origins or boundary conventions differ between model,
database, API, UI and export. A model may return frame indices, clip-relative seconds, or a mix; a video
player seeks in source time. Humans also need to correct boundaries without destroying the model output.

## Decision

1. **Unit:** float seconds.
2. **Origin:** the start of the **source video** (never a clip, never wall-clock).
3. **Interval:** half-open `[start, end)`; invariant `0 ≤ start < end ≤ duration` enforced on write.
4. **Rounding:** 3 decimals (ms).
5. **Three families, never overwritten:**
   - `proposal` (model output, after bound clamping),
   - `preview` (padded window cut to a clip),
   - `corrected` (human edit).
6. **Effective label** = `corrected` if present else `proposal`. `preview` is never a label.
7. `duration_seconds` is probed server-side with ffmpeg and stored on the video.

## Consequences

- One validation module (`app/validation.py`) is used by the pipeline, the annotation API and the export.
- The UI must convert only for display; it never invents boundaries.
- Export includes all three families plus `final`, so the dataset is auditable.
- Model adapters must re-base their internal window times to source time themselves; the worker validates.

## Alternatives rejected

| Option | Why not |
|---|---|
| Frame indices | Frame rate varies, VFR video breaks assumptions |
| Clip-relative seconds | Ambiguous after padding/correction; not comparable across candidates |
| Single "start/end" overwritten by review | Loses the proposal; makes model evaluation impossible |
| Closed interval `[start, end]` | Off-by-one-second ambiguity at boundaries and zero-length subtleties |

## Verification

`backend/tests/test_validation.py`, `test_flow.py`, and the export assertions in `scripts/smoke_e2e.py`.
