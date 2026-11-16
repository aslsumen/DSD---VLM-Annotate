# VLM Annotate — Project Plan v1

*AI proposes. Humans decide. Datasets you can defend.*

Course deliverable D-01 · version 1.0 · built 2026-11-05
The 2026-11-02 23:59 upload deadline was missed; this deck is delivered late and transparently.
Customer: Gordan Kreković / Visage Technologies · DSD 2026/2027
Team names, capacity and time zones are still placeholders (see working agreements).

---

## 1. Long video is cheap. Precise labels are not.

> A 30-minute interview or training session takes hours to annotate by hand — and a model that labels on its own is not trustworthy enough to ship.

## 2. The problem we are solving

*Context*

**Today**

- Reviewers scrub timelines frame by frame
- Model output is unverifiable black-box labels
- No provenance: which model, which prompt, which boundaries?
- Datasets quietly contain unlabelled items treated as negatives

**What we will build**

- VLM proposes timestamped candidates
- Human marks true / false positive
- Unreviewed stays visibly unreviewed
- Export carries clips, labels and provenance

<!-- speaker notes: Frame the product as a human-in-the-loop annotation tool, not a model demo. -->

## 3. Who it is for

*Users*

**Customer**

- Gordan Kreković / Visage Technologies
- Needs a repeatable way to produce action datasets
- Cares about correctness and auditability
- No sign-off recorded yet — open questions on the last slides

**Primary personas**

- Dataset builder: uploads and describes
- Reviewer: decides TP/FP quickly
- Supervisor: checks progress and provenance
- Distributed developer: integrates via REST

## 4. One workflow, seven steps

*Product*

- Create a project and an action definition in natural language
- Upload a single-view RGB video (10–30 minutes target)
- Start asynchronous VLM processing — the browser never waits
- Receive candidate intervals in source-video seconds with preview clips
- Review each candidate: true positive, false positive, or leave unreviewed
- Correct boundaries when the model is close but not right
- Export a dataset ZIP with labels, media and provenance

<!-- speaker notes: This is the demo script for later sprints; every step exists in the Sprint 2 slice except real inference. -->

## 5. MVP now, options only after the gates

*Scope*

| MVP (Sprint 2–3) | Later (Beta/Final) | Explicitly out |
|---|---|---|
| Projects, actions, upload | Real VLM quality tuning | Tracking / identity |
| Async jobs with retries | Reliability + retention | Multi-camera |
| Candidates + preview clips | Acceptance evidence | Audio analysis |
| TP/FP review, unreviewed | Deployment packaging | Fine-tuning |
| Dataset export + provenance | Final report | Multi-model comparison UI |

_Optional features are frozen until the MVP gate passes — a course requirement, not a preference._

## 6. How we will know it works

*Success*

| Criterion | Target | How measured |
|---|---|---|
| Responsive under load | HTTP enqueue < 300 ms | Smoke timing, job stays 202 |
| Timestamp validity | 100% inside [0, duration] | Automated + export validation |
| No silent negatives | No code path can do it | Schema design + tests |
| Export usable offline | ZIP with manifest + clips | Unzip and play in smoke test |
| Reproducible install | Documented commands | Fresh-machine run |
| Model quality | Measured recall/precision | Alpha evaluation set |

## 7. Three units, two kinds of state

*Architecture (provisional)*

- Web UI: React + TypeScript, responsive, hash routing
- API: FastAPI — validation, auth, range streaming, enqueue only
- Worker: separate process — claims jobs, calls the adapter, cuts clips
- Database: projects, videos, jobs, candidates, annotations, exports
- Storage: generated keys for source videos, clips, archives
- Model logic isolated behind one VLMAdapter interface

_Provisional until the Design Description v1 review on 2026-11-13._

## 8. Time is the contract

*Correctness*

- All times: seconds relative to the source video, half-open [start, end)
- Proposal, preview and human correction are stored separately
- Effective label = correction if present, otherwise proposal
- Every interval validated: 0 ≤ start < end ≤ duration
- Preview clips are context, never the label

## 9. Unreviewed never becomes negative

*The guarantee*

> There is no is_negative column. A label exists only as an annotation row created by a person; export excludes everything else unless explicitly told otherwise.

## 10. Delivery plan against the official calendar

*Plan*

| Sprint | Ends | Presentation | Increment |
|---|---|---|---|
| 1 | 2026-11-01 | 11-03 Vision/Plan | Plan + backlog (late) |
| 2 | 2026-11-15 | 11-10 Req & Design | Runnable mock vertical slice |
| 3 | 2026-11-29 | 12-01 Alpha | Real VLM + evaluation |
| 4 | 2026-12-13 | 12-15 Beta | Reliability, acceptance plan |
| 5 | 2026-12-27 | none | Acceptance plan due 12-25 |
| 6 | 2027-01-10 | 01-12 Final | Release candidate, test report |
| 7 | 2027-01-17 | none | Final product + ≤20-page report |

## 11. How a distributed team will work

*Team*

**Organisation (placeholders)**

- Product Owner and Scrum Master
- Backend, frontend, ML/adapter, QA, DevOps
- One owner and one backup per subsystem
- Capacity table to be filled by 2026-11-06

**Working rules**

- Stable REST contract before parallel UI/worker work
- Small reviewable changes; ADRs for decisions
- Written async stand-ups across sites
- Tests and evidence, never verbal status

## 12. What can go wrong

*Risk*

| Risk | Impact | Response |
|---|---|---|
| Course guidelines behind FER login | Decks may not match rules | Human download by 11-06 |
| 8 GB GPU cannot run 7B VLM | Alpha slips | 3B/4-bit or SmolVLM2 fallback |
| No capacity data yet | Plan unachievable | Fill table, rebalance 11-11 |
| Late Project Plan deck | Compliance | Upload now, notify supervisor |
| No real long footage tested | Unproven NFR | Validate by 11-13 |

## 13. What we need to decide with the customer

*Customer*

- Clip definition: tight action only, or padded context?
- Which action types first — sports, interviews, surveillance?
- True maximum video length: 30 minutes or longer?
- Required dataset format: COCO, ActivityNet, custom JSONL?
- Do reviewers need an 'uncertain' label as a third state?

_Tracked as Q-01…Q-05 in docs/REQUIREMENTS.md._

## 14. What we need this week

*Ask*

- ☐ Download the three official guideline files from the FER materials page
- ☐ Confirm team names, roles, capacity and time zones
- ☐ Grant supervisors access to the living backlog and burndown
- ☐ Confirm the customer's answers to Q-01…Q-05
- ☐ Confirm the late Project Plan upload with the supervisor

## 15. Where we actually are

*Status*

> Sprint 1 produced no software (none was required) and missed its one hard deadline. Sprint 2 already has a runnable, tested vertical slice — with mock candidates, clearly labelled.
