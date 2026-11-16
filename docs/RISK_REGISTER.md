# Risk Register

**Type:** living artifact · **Last updated:** 2026-11-16 · **Owner:** Scrum Master (role placeholder)
Score = probability (1–5) × impact (1–5). Reassess at every sprint review.

## 1. Open risks

| ID | Risk | Prob | Impact | Score | Owner | Mitigation / next action | Status |
|---|---|---|---|---|---|---|---|
| **R-01** | Official `Guidelines (SCRUM, Presentations)` files are behind a FER login wall; decks/documents may violate real slide/document rules | 5 | 5 | **25** | Scrum Master | A team member downloads the three files + templates by **2026-11-06**; checklist updated; decks re-validated before upload | **OPEN — blocking** |
| **R-02** | No real 10–30 min customer-like footage tested; only a 2-min synthetic clip | 4 | 4 | **16** | QA | Produce/obtain 1–2 consented long videos by 2026-11-13; record duration/probe/clip results; mark NFR-02 accordingly | **OPEN** |
| **R-03** | Real VLM inference not validated on product footage; 8 GB VRAM may be too slow or low quality | 3 | 5 | **15** | ML | 2026-11-16: VideoJev-4B integrated as the `videojev` adapter (ADR-0007), runs on the 8 GB laptop with CPU offload; backend tests (fake engine) and engine tests pass. Still open: real-model smoke on the RTX 3070 laptop (`scripts/smoke_videojev.py`) and 10–30 min product footage (R-02); never ship mock as "AI" | **OPEN — mitigating** |
| **R-04** | Team capacity and names unknown; plan may be unachievable or unbalanced | 5 | 4 | **20** | Scrum Master | Fill capacity table by **2026-11-06**; rebalance at 11-11; 80–85 % loading rule | **OPEN** |
| **R-05** | Project Plan v1 deck missed its 2026-11-02 deadline and was never uploaded | 5 (occurred) | 4 | **20** | Product Owner | Upload immediately, notify supervisor, record evidence, note root cause in Sprint 1 retro | **OCCURRED — mitigating** |
| **R-06** | No retention/purge policy enforcement; disk fills with videos, clips, exports | 3 | 3 | **9** | Backend | PB-27 purge job in Sprint 4; document manual cleanup now | **OPEN** |
| **R-07** | Worker crash leaves a job `running` forever (no stale-job reaper) | 3 | 3 | **9** | Backend | PB-28 done 2026-11-16: heartbeat lease (`updated_at` every `VLM_WORKER_HEARTBEAT_SECONDS`), jobs silent for 3 beats are requeued as `WORKER_LOST` or failed when attempts are exhausted (ADR-0001 amendment) | **MITIGATED** |
| **R-08** | Only Windows has been verified; macOS/Linux setup may differ (paths, ffmpeg, venv) | 3 | 2 | **6** | DevOps | Installation manual states Windows as verified; add container packaging (PB-30) | **OPEN** |
| **R-09** | PostgreSQL path untested; SQLite-only assumptions (single writer, no SKIP LOCKED) | 2 | 3 | **6** | Backend | Migration/claim design documented; add a Postgres CI job when deployment needs it | **ACCEPTED** |
| **R-10** | Model licence mismatch (Qwen2.5-VL-3B is `qwen-research`, not Apache) | 1 | 4 | **4** | ML | 2026-11-16: the shipped detector is VideoJev-4B (Apache-2.0, revision pinned), ADR-0007; Qwen2.5-VL stays a stub, so its licence is not in play. Re-check the VideoJev model card licence before shipping weights | **MITIGATED** |
| **R-11** | Mock candidates are mistaken for real model output in a demo/report | 3 | 4 | **12** | All | MOCK banner in UI, `provenance.mock` in manifest, wording in decks/docs, review checklist | **MITIGATED (verify in demo)** |
| **R-12** | Product Backlog / Sprint Backlog / burndown are local files; supervisors cannot access them | 4 | 4 | **16** | Product Owner | Create shared board or grant repo read access by **2026-11-07**; record the link in the register | **OPEN** |
| **R-13** | Frontend dependency/toolchain churn breaks the build close to a deadline | 3 | 3 | **9** | Frontend | Lockfile committed; `npm ci` documented; build verified in CI/local before uploads | **OPEN** |
| **R-14** | ffmpeg codec variance: some inputs/produce clips browsers cannot play | 3 | 3 | **9** | Media | H.264/AAC output with `+faststart`; per-candidate `clip_error`; source-video fallback in review UI | **MITIGATED** |
| **R-15** | Sprint Review/Retrospective format assumption (separate decks) is wrong | 2 | 3 | **6** | Scrum Master | A-01 in guidelines checklist; merge/adjust after real guidelines are read | **OPEN** |
| **R-16** | Export of large clips exceeds memory/disk or times out | 2 | 3 | **6** | Backend | Streaming ZIP, `max_export_bytes`, async export; test with a larger dataset in Sprint 4 | **OPEN** |
| **R-17** | Course calendar changes (new announcement) invalidates the plan | 2 | 4 | **8** | Scrum Master | Weekly check of the course page; calendar doc has a "last verified" date | **OPEN** |
| **R-18** | Token-protected deployment breaks video review: `<video src>` cannot send the bearer header, so stream/clip return 401 | 4 | 3 | **12** | Backend/Frontend | Implement short-lived signed media URLs or a session cookie (PB-41); until then document "do not set `VLM_API_TOKEN` for demos that need playback" | **OPEN** |
| **R-19** | **Scope pivot (2026-11-09):** the new MVP requires users, global roles, invitations, datasets, searches and OpenLABEL JSON, while the working slice uses projects/actions and a shared token | 5 | 5 | **25** | Product Owner / Architect | Treat the current slice as a reusable technical prototype; plan the domain/auth rework in Sprint 3; re-baseline the MVP gate with the supervisor | **OPEN — top risk** |
| **R-20** | No written approval to send face-containing videos to the Gemini API (NFR-8) | 5 | 5 | **25** | Product Owner | Ask the customer on 2026-11-13; use only public/team footage for API experiments until approval | **OPEN — blocking** |
| **R-21** | Gemini key expired before redemption or leaked; free-tier quota insufficient | 3 | 4 | **12** | Backend | Check redemption now; request a new key via the secure channel; store only in environment; add quota guard/backoff | **OPEN** |
| **R-22** | Timeline: USR-1…USR-7 are **Must** in v1.1 but Sprint 2 ends 2026-11-15 | 5 | 5 | **25** | Scrum Master | Declare the Sprint 2 gate a technical prototype (per course wording "prototype growing in fidelity"); move the new MVP scope to Sprint 3–4; inform supervisor | **OPEN** |
| **R-23** | 12 GB VRAM offered vs 24 GB assumed for quantised VideoJev-4B | 2 | 4 | **8** | ML owner | 2026-11-16: VideoJev-4B runs on an 8 GB RTX 3070 laptop with CPU offload (`configs/rtx3070.yaml`), about 0.66× the video duration on Charades-STA (EVALUATION.md); no quantisation needed. Slow, not a reference setup; a GPU worker is still needed. Peak VRAM at current sampling not recorded | **MITIGATED** |
| **R-24** | Test-dataset licences are non-commercial (Charades/Charades-STA, DMD); commercial use unclear | 4 | 3 | **12** | ML owner | Ask the customer; use MEVA (CC-BY-4.0) for public demos; never redistribute restricted videos | **OPEN** |
| **R-25** | OpenLABEL schema mismatch discovered late; the customer's example is still missing from the repo | 4 | 4 | **16** | Architect | Send the one-page schema proposal by 2026-11-17; confirm multi-interval, reviewer, clips before implementing | **OPEN** |
| **R-26** | Detection quality below KPI targets (recall/R@IoU) | 5 (occurred) | 5 | **25** | ML owner | 2026-11-16: measured on Charades-STA (300 videos, 822 queries, `min_event_score` 0.9): recall 0.690, R1@0.5 0.460, CCR 0.778 vs targets 0.85 / 0.70 / 0.85 (EVALUATION.md). Lowered the default to 0.5; rerun: recall 0.771, R1@0.5 0.507, CCR 0.786, still below target. Short events (< 5 s) are the main loss (recall 0.58). Customer accepts model limits; human review mandatory; only Charades-STA measured, not product footage | **OCCURRED — mitigating** |

## 2. Top risks and what happens this week

1. **R-19 / R-22 (scope pivot + timeline)** — the customer's answers expand the MVP beyond what Sprint 2 can
   deliver. Decide with the supervisor whether the Nov 15 gate is met by a testable technical prototype.
2. **R-20 (privacy approval)** — without it the Gemini API cannot be used on customer footage. Detection is self-hosted and Gemini verify is off in the `videojev` adapter, so it matters only if verify is turned on.
3. **R-01 / R-12 (guidelines + supervisor access)** — course-compliance issues no code can fix.
4. **R-26 (detection quality)** — the core value; measured on Charades-STA (below SPEC targets, EVALUATION.md); not yet on product footage.

## 3. Closed / accepted

| ID | Decision | Date |
|---|---|---|
| R-09 | SQLite is accepted for the course deployment; PostgreSQL remains a documented path | 2026-11-05 |
| R-11 | Mock is acceptable **only** when labelled; not a risk if the label is present | 2026-11-05 |

## 4. Risk review log

| Date | Change |
|---|---|
| 2026-11-05 | Register created; R-05 recorded as occurred (missed deck deadline) |
| 2026-11-16 | R-03, R-10, R-23, R-26 updated after the `videojev` adapter integration (ADR-0007) and the Charades-STA measurements; R-26 occurred (below KPI targets) |
