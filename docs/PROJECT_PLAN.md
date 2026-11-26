# Project Plan (supporting document)

> **This file is not course deliverable D-01.** The Project Plan v1 is a **versioned slide deck**, delivered as
> `presentations/01-project-vision-plan-v1.pptx` (built late on 2026-11-05; the 2026-11-02 deadline was
> missed and the upload is still pending). This document holds the narrative behind those slides.

## 1. Vision

Make labelled temporal-action datasets from long videos with **AI proposals and human decisions**: a reviewer
should be able to turn a 30-minute interview or training session into a verified set of action clips in
minutes, without scrubbing the whole timeline and without trusting a model's labels.

## 2. Problem and customer

Long, single-view RGB video is cheap; precise temporal annotation is expensive. Existing tools either require
frame-level manual work or produce unverifiable model output. Visage Technologies (customer, via the DSD
course) needs a workflow where a VLM proposes candidates, a human verifies them, and the exported dataset
carries provenance that makes the labels auditable.

**Customer sign-off:** none recorded yet. Requirements are derived from the project brief; open questions are
tracked in [REQUIREMENTS.md §10](REQUIREMENTS.md#10-open-questions-for-the-customersupervisor).

## 3. Users

- **Dataset builder** — uploads videos, writes action descriptions, monitors jobs.
- **Reviewer** — decides true/false positive quickly, with keyboard support.
- **Supervisor / project owner** — checks progress, provenance and export quality.
- **Team member (distributed)** — integrates against a stable REST contract.

## 4. Scope

**MVP** (Sprint 2 gate, 2026-11-15): projects, actions, upload/probe, asynchronous jobs, timestamped
candidates with playable previews, TP/FP review with an explicit unreviewed state, dataset ZIP with
provenance, responsive UI.

**Alpha** (2026-11-29): real VLM inference on representative footage (VideoJev-4B via the `videojev` adapter, ADR-0007,
replacing the earlier windowed Qwen2.5-VL plan; integrated 2026-11-16, held-out long-video benchmark measured 2026-11-22: recall 0.86 cooking (CI 0.81–0.90) / 0.47 driving vs target 0.85, driving weak; Charades-STA serves as a reference. A 52-second public clip passed the VideoJev web smoke on the RTX 3070 laptop on
2026-11-23), evaluation metrics, reliability work.

**Beta → Final**: acceptance tests, installation/deployment docs, hardening, final report.

**Optional, only after MVP gates**: multiple VLMs and comparison UI, bulk review, fine-tuning, tracking,
multi-camera, audio, analytics (see backlog OPT-01…OPT-06).

## 5. Success criteria

| Criterion | Target | Current status |
|---|---|---|
| Long video handled asynchronously | UI stays responsive during a 30-min job | Achieved by architecture; 2-min real test PASS, 10–30 min **NOT YET TESTED** |
| Candidate timestamps valid | 100 % of exported items satisfy `0 ≤ start < end ≤ duration` | PASS in automated + smoke tests |
| Unreviewed never becomes negative | No code path can produce a negative from a missing label | PASS (schema design + tests) |
| Export usable outside the app | ZIP with manifest, CSV, clips | PASS (26/26 smoke checks) |
| Reproducible install | Documented commands on a clean machine | Windows verified; other OS untested |
| Real model quality | Measured recall/precision on a ground-truth set | Held-out long-video benchmark measured 2026-11-20 to 22 (VideoJev-4B, verify off; YouCook2 33 videos, ROAD 20): recall 0.86 [0.81, 0.90] cooking, 0.47 [0.39, 0.56] driving vs target 0.85; CCR 0.78 / 0.82 vs 0.85; cooking recall meets the target only as a point estimate, the other three miss; absent prompts still give 3.5 (cooking) and 8.4 (driving) candidates (`video_grounding/docs/EVALUATION.md`); earlier small composites (2026-11-17) are superseded; Charades-STA (recall 0.690 at the time) is reference only, VideoJev was trained on it; **product footage NOT MEASURED** (Alpha gate) |

## 6. Delivery schedule (course calendar)

| Sprint | Ends | Presentation | Our increment target |
|---|---|---|---|
| 1 | 2026-11-01 | 11-03 Intro/Vision/Plan | Plan, backlog, decks (delivered late) |
| 2 | 2026-11-15 | 11-10 Requirements & Design; 11-17 Status | Requirements/design baseline + runnable mock slice |
| 3 | 2026-11-29 | 12-01 Alpha | Real inference + evaluation evidence |
| 4 | 2026-12-13 | 12-15 Beta | Reliability, acceptance test plan, hardening |
| 5 | 2026-12-27 | none | Acceptance test plan (12-25) before holidays |
| 6 | 2027-01-10 | 01-12 Final | Acceptance report (01-04), release candidate |
| 7 | 2027-01-17 | none | Final product, installation docs, ≤20-page report |

## 7. Team organisation and Scrum flavour

- Roles: Product Owner, Scrum Master, backend, frontend, ML/adapter, QA, DevOps — **role placeholders only**
  until the team supplies names and capacity (`docs/TEAM_WORKING_AGREEMENTS.md`).
- Scrum elements we commit to now: sprint backlog, daily async stand-up, sprint review + retrospective
  artifacts, product backlog refinement, burndown.
- Mandatory/optional Scrum elements depend on `DSD SCRUM elements`, which is behind a login wall (`R-01`).
  **Provisional** until inspected.

## 8. Distributed-team approach

- Stable REST + typed schemas first, UI and worker consume the same contract.
- One owner + one backup owner per subsystem (backend, frontend, ML, QA).
- Small, reviewable changes; decisions recorded in `docs/decisions/`.
- Async stand-ups with written updates; shared evidence in `docs/evidence/`.
- Overlap window for pair reviews: **TBD** (needs team time zones).

## 9. Risks

Top risks: inaccessible course guidelines (R-01), unknown capacity (R-04), real inference feasibility on 8 GB
VRAM (R-03), supervisor access to living artifacts (R-12). Full register:
[RISK_REGISTER.md](RISK_REGISTER.md).

## 10. Infrastructure and cost

Local development only: no cloud spend, no paid API. A GPU rental is a contingency for model evaluation only
(not budgeted). Storage: local disk; 30-minute 1080p source ≈ 1–2 GB plus clips.

## 11. What "done" means for the course

Final product + installation docs + ≤20-page report on 2027-01-17, with the deck/doc trail from every sprint,
the acceptance test plan/report, and living Scrum artifacts that supervisors could access throughout.
