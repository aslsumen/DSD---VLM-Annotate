# Model and Test-Data Evaluation

**Status:** v1.2 working note · **Date:** 2026-11-12 · **Owner:** ML/adapter workstream (role placeholder)
**Real inference on project videos:** **NOT RUN** — the repository still uses the labelled mock adapter.

> This document separates three things that are easy to confuse: what a model *claims*, what we have
> *verified in a primary source*, and what we have *measured ourselves*. Only the last one is evidence of
> quality, and we have none yet.

> **As-built detail for the implemented prototype:** [docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md](as-built/IMPLEMENTED_BASELINE_2026-11-05.md).

## 1. What changed on 2026-11-12

| Change | Source | Consequence |
|---|---|---|
| Customer supplied a **Gemini API key** (Google AI Studio, free tier) | Customer email CE-2 | An API-based detector is now a viable first implementation; privacy approval still required |
| Team design names **VideoJev-4B** as the reference self-hosted model (Apache-2.0, Qwen3.5-4B base) | Design Description v1.1 §6.1.1 | Self-hosted path has a concrete candidate; model card still to be verified by the team |
| Supervisors offer **12 GB VRAM laptops** immediately; remote access TBD; AWS possible | Supervisor emails 2026-11-04/05/09 | 7–8 B bf16 does not fit; 4 B quantised or API is the realistic path |
| Team memo selects **test datasets** and flags licences | `docs/inputs/2026-11-12/Datasets.pdf` | Charades-STA for the pipeline, TimeLens-Bench for KPIs; commercial use unresolved |

## 2. Hardware reality (measured / offered)

| Resource | Value | Implication |
|---|---|---|
| Project laptop GPU | RTX 4060 Laptop, **8 GB**, driver 621.01 | 4 B in bf16/4-bit only; 7–8 B does not fit |
| CPU / RAM | Ryzen 7 7735HS, 8C/16T, 15.3 GB | CPU inference slow; fine for dev |
| University offer | **12 GB VRAM laptops**, immediate | 4 B bf16 fits; 7 B only 4-bit; remote access unresolved |
| Team estimate sent to supervisors | 24 GB GPU, 32 GB RAM, 512 GB–1 TB storage | Conflicts with the 12 GB offer → either smaller model or cloud/API |
| Gemini API | Free tier: ~3,600 images/request at 258 tokens/image, 1M TPM, 1,500 req/day | Sufficient for development and KPI samples; not for mass processing of long video |

## 3. Model options

| Option | Licence | Temporal grounding evidence | Fit | Status |
|---|---|---|---|---|
| **Gemini API** (Flash-class model) | Commercial API terms; customer-provided key | Not verified for temporal grounding; prompt/schema must be tested | No local GPU needed; quota-bound | **Candidate for first real detector** |
| **VideoJev-4B** (MCG-NJU, Qwen3.5-4B base) | Apache-2.0 per team design | Team design says it returns a **per-frame-pair probability curve** plus one interval — suited to windowed fusion | 4 B; needs ~8–16 GB depending on quantisation | **Reference self-hosted candidate; card to verify** |
| Qwen2.5-VL-7B / 3B | 7B Apache-2.0; **3B `qwen-research`** | Card claims segment pinning, mRoPE absolute time, Charades-STA mIoU 43.6 (row malformed); fps passed to processor | 7B no; 3B yes | Fallback/comparator |
| SmolVLM2-2.2B | Apache-2.0 | No grounding claim; card documents **5.2 GB** video inference | Yes | Presence-classifier fallback |
| InternVL3.x / LLaVA-Video / VideoLLaMA3 | Apache/MIT mix | No temporal-grounding claim | Mostly no | Describe-only; not timestamp sources |

> **Verified vs reported.** The Qwen2.5-VL and SmolVLM2 facts were read from their official Hugging Face cards
> on 2026-11-05 (links in §10). The VideoJev-4B facts come from the team's Design Description v1.1 and are
> **not independently verified here**; verify the card, revision hash and licence before implementing.

## 4. Why a score curve matters

A model that returns one interval per prompt cannot find repeated occurrences (ENG-3) nor prove that a clip
contains the whole action (ENG-6). VideoJev-4B's reported per-pair probability curve allows:

- detecting **all** occurrences (each peak is an event);
- fusing overlapping windows on one timeline (Design §6.1.5);
- flagging boundaries seen only at a window edge or with sparse sampling;
- re-thresholding without re-running inference (ENG-8).

Gemini-class chat APIs return text, not a calibrated curve; any timestamps must be parsed from JSON and
validated. That is acceptable for a first MVP but must be measured, not assumed.

## 5. Decision (working, supersedable)

| Layer | Decision | Rationale |
|---|---|---|
| Sprint 2 prototype | **Mock adapter only**, labelled | Pipeline and review correctness first |
| First real detector (Sprint 3) | **Gemini API** behind the `GroundingBackend` interface, on **non-sensitive test videos only** | No GPU dependency, fastest path to measured KPIs; key already provided |
| Self-hosted target (Sprint 3–4) | **VideoJev-4B** quantised on the 12 GB laptop (or 24 GB GPU if granted), for customer footage and privacy | Apache-2.0, score curve, offline (ENG-12) |
| Comparator | Qwen2.5-VL-3B or SmolVLM2 windowed presence | Licence/feasibility fallback |
| Forbidden | Sending face-containing customer footage to any API without written approval | NFR-8 |

**Blocking question for the customer (13 Nov):** may videos that show faces be sent to Gemini? Until answered,
use public/team footage for API experiments and keep the self-hosted path for customer data.

### 5.1 Update 2026-11-16: VideoJev-4B integrated as the `videojev` adapter

[ADR-0007](decisions/ADR-0007-videojev-zero-shot-grounding-adapter.md) plugs the `video_grounding/` engine into
the job queue. Why VideoJev-4B: it is a temporal-grounding model with a score curve, and it runs on an 8 GB
laptop GPU with CPU offload. Evidence, Charades-STA test subset (300 videos / 822 queries), before verification:
recall 0.690, precision 0.768, R1@0.3/0.5/0.7 = 0.683/0.460/0.215, mIoU 0.437, about 1.3x video duration
processing time on an RTX 3070 Laptop 8 GB (details: `video_grounding/docs/EVALUATION.md`). These numbers use
`min_event_score` 0.9; a re-run with the new default 0.5 is in progress (offline estimate: recall 0.771).
Gemini verification stays off by default. The Qwen2.5-VL comparator row above is not implemented.

## 6. Gemini API operations and security

- **Key handling:** the key arrived through a one-time secure link (24 h). It must live only in the backend
  environment (`VLM_GEMINI_API_KEY`) or a secret store — **never in Git, chat logs, screenshots or docs**. If the
  link was not redeemed in time, request a replacement; the 2026-11-09 link has almost certainly expired.
- **Quota:** free tier limits are per Google account; development traffic must be rate-limited and cached.
  Design the adapter with retry/backoff on 429 and a per-day budget guard.
- **Determinism:** fixed model version, temperature 0 where supported, prompt template versioned in
  `ModelConfig`.
- **Data:** API calls leave the machine; log only hashes/ids of videos in development, never the footage.
- **Cost:** if the free tier is insufficient, the customer said additional budget can be assigned; do not
  assume it.

## 7. Test datasets and licences (from the team memo)

| Dataset | Content | Fit | Licence caveat |
|---|---|---|---|
| **Charades-STA** | Short indoor videos with sentences tied to start/end times; videos included (16.3 GB) | **Best first test set** — exactly text→interval | Repo says MIT, but the underlying Charades videos are **non-commercial research only** |
| Charades | 9,848 videos, 157 action classes with start/end | Same videos with class labels; "Opening a door" matches the customer example | **Non-commercial research only; no redistribution** |
| **TimeLens-Bench** | Manually refined Charades-STA + ActivityNet Captions + QVHighlights annotations | **Best for KPIs** (clean annotations) | BSD-3-Clause for annotations; videos come from source datasets (their licences apply) |
| MEVA | Surveillance, 37 activity types, 22 h public annotations | Closest to warehouse/surveillance domains | **CC-BY-4.0** (most permissive) |
| DMD | Driver monitoring: distraction/fatigue actions | Closest to driver-monitoring domain | **CC BY-NC-ND 4.0**, academic only, RGB only |
| UCA (UCF-Crime Annotation) | 23,542 sentences over 110.7 h | Large surveillance set | Access via project site; terms to check |

**Licence question for the customer:** is commercial use required? If yes, Charades/Charades-STA are
development-only and results cannot be redistributed; MEVA (CC-BY-4.0) is the safest for demos. The customer's
own footage (with permission) is the only fully realistic test for their domains.

## 8. Evaluation protocol (not yet executed)

| Item | Definition |
|---|---|
| Ground truth | 20–30 hand-labelled clips across 3–5 videos, two action types, boundaries to ±0.5 s |
| Metrics | Event recall, R@IoU 0.3/0.5/0.7, precision (accept rate), complete-clip rate, boundary adjustment (seconds), proposals per minute, latency, peak VRAM |
| Protocol | One prompt per video; windowed inference with fixed config; record model revision and prompt template |
| Reporting | `docs/MODEL_EVALUATION_RESULTS.md` with raw outputs, config and date; no metric is reported without the exact command/config |
| Reference | Charades-STA for pipeline bring-up; TimeLens-Bench for KPI comparison; MEVA/DMD for customer-domain demos |

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No written approval for cloud API on face videos | Blocks API detector | Use test footage; self-hosted VideoJev for customer data |
| Gemini timestamps are guesses, not grounding | Bad candidates | Measure on Charades-STA; validate JSON; keep human review mandatory |
| VideoJev-4B does not fit 12 GB / card facts wrong | Rework | Verify card + quantised run in Sprint 3; Qwen3B/SmolVLM2 fallback |
| Test-dataset licences non-commercial | Cannot publish results | Clarify with customer; use MEVA for demos |
| Key expiry/leak | Operational and security incident | Secure channel, env vars, rotation, never commit |
| KPI targets unconfirmed | Cannot declare success | Confirm on 13 Nov |

## 10. Sources

- Requirements Definition v1.1 and Design Description v1.1 — `docs/inputs/2026-11-12/` (team documents)
- Datasets memo — `docs/inputs/2026-11-12/Datasets.pdf` (team document)
- Qwen2.5-VL-7B-Instruct card — <https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct> (fetched 2026-11-05)
- SmolVLM2-2.2B-Instruct card — <https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct> (fetched 2026-11-05)
- Qwen2.5-VL-3B-Instruct licence field `qwen-research` — <https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct>
- Hardware: local `nvidia-smi` / CIM query, 2026-11-05; supervisor emails 2026-11-04/05/09
- Customer email CE-2 (Gemini access) — transcribed in `docs/customer/CUSTOMER_DECISIONS.md`
