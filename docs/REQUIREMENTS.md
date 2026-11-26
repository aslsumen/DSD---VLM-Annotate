# Requirements Definition — working repository copy

**Project:** VLM Annotate · **Customer:** Visage Technologies (Gordan Kreković)
**Version:** 1.2 (repository working copy) · **Date:** 2026-11-15 · **Status:** v1.1 PDFs delivered to the team (submission evidence unverified); this copy adds the 9 Nov customer answers
**Supersedes:** this repository's v1.0 (2026-11-05). **Aligned with:** team's Requirements Definition v1.1
(`docs/inputs/2026-11-12/VLM_Annotate_-_Requirements_Definition_v1.1.pdf`) **plus** the latest customer reply
(CE-2).

> **Why v1.2 exists.** CE-2 answers four questions left open in v1.1: Dataset Administrators may invite users;
> roles are global; accounts are email-only; and the workflow is explicitly non-continuous. No customer
> approval is claimed for anything not written in the emails.

Priority scale: **Must** = MVP · **Should** = after the MVP works · **Could** = if time allows.
Source codes: **CP** customer proposal · **CM** meeting 2026-10-30 · **CE-1** email 2026-11-05 · **CE-2** latest
email · **T** team.

> **As-built detail for the implemented prototype:** [docs/as-built/IMPLEMENTED_BASELINE_2026-11-05.md](as-built/IMPLEMENTED_BASELINE_2026-11-05.md).

## 1. Purpose, context and terms

VLM Annotate is a web application that uses zero-shot VLMs to find events described in plain language in
videos. The model proposes candidate events with timestamps; a person reviews them, adjusts the timestamps and
accepts or rejects them. The result is a labelled dataset exported as JSON for training downstream models.

**Terms**

- **Dataset** — a collection of videos uploaded for one use case.
- **Search** — one prompt run over all videos of a dataset; a dataset can have several searches.
- **Event** — an action/situation with a start and an end.
- **Candidate** — a proposed segment awaiting review.
- **Annotation** — a reviewed candidate (accepted or rejected) with its final timestamps.
- **Zero-shot** — detection from the text prompt without training on the target event.

**MVPs:** the complete loop **sign-in → dataset → prompt → detection → review → JSON export**.

## 2. Users, roles and permissions

Accounts are created **only by invitation**. There are two base roles and one optional role; the Viewer role
was removed. **Roles are global** (CE-2): a person has one role across the platform. A Dataset Administrator
who must annotate a dataset they do not manage uses a separate account with the global Annotator role.

| Role | Goal | MVP |
|---|---|---|
| Administrator | Manage users, roles and all datasets | Yes |
| Dataset Administrator | Manage only datasets they uploaded or were assigned; assign annotators to them | Should (after the MVP works) |
| Annotator | Review candidates and validate annotations in assigned datasets | Yes |

| Functionality | Administrator | Dataset Administrator | Annotator |
|---|---|---|---|
| Invite users / manage accounts and roles | Yes | **Yes — within their own datasets (CE-2)** | No |
| See the list of annotators | Yes | Yes | No |
| Assign datasets to users (incl. Dataset Admins) | Yes | No | No |
| Assign annotators to datasets | Yes | Yes (only datasets they can access) | No |
| Create and manage datasets | Yes | Yes (own scope) | No |
| Upload videos | Yes | Yes (own scope) | No |
| Define prompts / initiate VLM processing | Yes | Yes (own scope) | No |
| Access datasets | All | Own scope | Assigned only |
| Review candidates / adjust timestamps / edit metadata | Yes | Yes (own scope) | Yes |
| Export validated datasets | Yes | Yes (own scope) | No |

## 3. Functional requirements

Status column: **I** implemented in the current repository · **P** partial · **N** not implemented.

### 3.1 Datasets and videos (DS)

| ID | Requirement | Priority | Source | Status |
|---|---|---|---|---|
| DS-1 | Administrator or Dataset Administrator uploads **MP4** videos into a dataset; Annotators cannot upload | Must | CP/CM/CE | **P** (upload works through `POST /datasets/{id}/videos` and now requires `administrator`/`dataset_admin`; MP4-only still not enforced) |
| DS-2 | Dataset = collection of videos, named after its use case; list of its videos | Must | CM/CE | **P** (`Dataset` entity + `GET /datasets/{id}/videos`; the name is free text and `use_case` was dropped in Design v1.2, so "named after its use case" is a convention, not a field) |
| DS-3 | User selects a dataset as the target of a search | Must | CM | **I** (a search is created against `dataset_id`; dataset selection exists in the API, UI pending) |
| DS-4 | Accept videos **up to 5 minutes** | Must | CM | **I** (limit is higher) |
| DS-5 | Accept videos **up to 30 minutes**; longer videos may be split | Should | CP/CM | **P** (limit configured; not validated on real 30-min footage) |

### 3.2 Prompts (PR)

| ID | Requirement | Priority | Source | Status |
|---|---|---|---|---|
| PR-1 | Administrator/Dataset Admin writes a free-text prompt describing a temporal event; several prompts can be run on the same dataset, each a separate search | Must | CP/CM/CE | **I** (`Search` entity: `searches.prompt` + auto `title`, one row per prompt run over a dataset, with per-video `search_videos` fan-out and aggregated status) |
| PR-2 | Edit a previous prompt and run it again on the same dataset | Could | T | **P** (the prompt is stored per search and a new search reuses it; editing a stored prompt is not offered) |

### 3.3 Detection (DET)

| ID | Requirement | Priority | Source | Status |
|---|---|---|---|---|
| DET-1 | Zero-shot detection without training a model for the event | Must | CP/CM | **P** (`videojev` adapter integrated 2026-11-16; mock is still the default; 52-second real-model web smoke passed on the 8 GB laptop on 2026-11-23; KPI check on held-out long videos 2026-11-22: recall 0.86 cooking (CI 0.81–0.90, not confirmed) / 0.47 driving vs 0.85, CCR 0.78 / 0.82 vs 0.85, targets not met, see `video_grounding/docs/EVALUATION.md`; Charades-STA is reference only) |
| DET-2 | Each candidate has start/end timestamps in the video, in minutes and seconds | Must | CP/CM | **I** (stored in seconds; UI formats) |
| DET-3 | Search runs in the background; user sees queued/running/done/failed and can leave the page | Must | CM/T | **I** (per-video jobs; dataset-level search missing) |
| DET-4 | Confidence score shown when available; candidates sortable by it | Could | T | **I** (score stored/sorted) |

### 3.4 Review (REV)

| ID | Requirement | Priority | Source | Status |
|---|---|---|---|---|
| REV-1 | Candidate preview: thumbnail and playback at the candidate timestamps | Must | CP/CM | **P** (clips + source player; no thumbnail) |
| REV-2 | Adjust start/end timestamps | Must | CM | **I** (corrected boundaries) |
| REV-3 | Accept or reject each candidate | Must | CP/CM | **I** (as true/false positive; vocabulary alignment pending) |
| REV-4 | Show reviewed/remaining counts | Should | T | **I** |

### 3.5 Export and video metadata (EXP)

| ID | Requirement | Priority | Source | Status |
|---|---|---|---|---|
| EXP-1 | Export accepted annotations of a dataset as **JSON** (dataset, video, prompt, start/end), based on the customer's OpenLABEL example; one action may have several intervals; only Admin/Dataset Admin | Must | CM/CE | **N** (current export is ZIP + manifest + CSV) |
| EXP-2 | Optionally include rejected candidates as negatives | Could | T | **P** (include-unreviewed flag exists; semantics differ) |
| EXP-3 | Automatic video summary and keyword tags for search/filter; may be included in export | Could (not MVP) | CM/CE | **N** |
| EXP-4 | Review/edit summary and tags | Could (lowest) | CE-2 | **N** |

### 3.6 Semantic search (SRCH)

| ID | Requirement | Priority | Source | Status |
|---|---|---|---|---|
| SRCH-1 | Find videos by scene description without precise timestamps (depends on EXP-3) | Should | CM | **N** |

### 3.7 Users and access (USR)

| ID | Requirement | Priority | Source | Status |
|---|---|---|---|---|
| USR-1 | Personal account; **sign in with email** (no username, CE-2) | Must | CE/T | **P** (login/session API; UI pending) |
| USR-2 | Two base roles with the permissions in §2; **roles are global** | Must | CM/CE | **I** (global `administrator`/`dataset_admin`/`annotator` enforced on the auth, dataset, search and — since 2026-11-25 — shared legacy video/job/candidate routes; UI pending) |
| USR-3 | Administrator assigns datasets to any user; users see only assigned datasets | Must | CM/CE | **P** (dataset memberships; annotators filtered) |
| USR-4 | Dataset Administrator: almost all rights within own datasets; sees all annotators; assigns only within own datasets; **may invite users (CE-2)** | Should | CE-2 | **P** (create dataset + invite annotators; UI pending) |
| USR-5 | Administrator (and Dataset Admin) enters email + role; system sends a single-use invitation; person sets password; account created | Must | T/CE-2 | **P** (single-use 48 h token; no mail transport yet) |
| USR-6 | Password reset by email | Should | T | **N** |
| USR-7 | Deactivate a user | Should | T | **N** (field exists, no endpoint) |

## 4. Non-functional requirements

| ID | Requirement | Target / validation | Priority | Status |
|---|---|---|---|---|
| NFR-1 | Desktop browsers Chrome, Firefox, Edge | Acceptance run in each | Must | **P** (Chrome headless only) |
| NFR-2 | Review usable on smartphone | Chrome Android + Safari iOS | Could | **P** (responsive at 375 px; not tested on devices) |
| NFR-3 | Search results within 24 h | Timed batch on the reference dataset | Must | **N** (no real detector) |
| NFR-4 | Accept HD 720p/1080p | Upload/process 1080p MP4 | Must | **P** (accepted; not enforced/tested) |
| NFR-5 | Detection quality measured by KPIs defined before testing | KPI report on a labelled set | Must | **N** |
| NFR-6 | Model replaceable without changing the workflow | Same search with two models | Should | **P** (adapter interface; `mock` and `videojev` adapters, Qwen2.5-VL stub; same search with two real models not tried) |
| NFR-7 | Candidates from all videos of a dataset in one filterable list | Review ≥ 20 videos from one list | Could | **P** (project-wide list; no pagination) |
| NFR-8 | Videos/annotations only on customer-approved infrastructure; external AI only with approval | Deployment review | Must | **P** (local storage; signed media links missing — R-18) |
| NFR-9 | Failed search shows an error and can be restarted | Simulated model failure | Should | **I** |
| NFR-10 | Installable by an outsider from the docs | Clean-machine install | Must | **P** (manual exists; no Docker) |
| NFR-11 | Passwords hashed; invitation links single-use, expire in **48 h** | Reuse/expire test | Must | **N** |
| NFR-12 | Sign-out from any page; protected pages/API refuse old session | Sign out and retry | Must | **N** |
| NFR-13 | Session expires after inactivity (proposed 2 h); no silent loss of unsaved review changes | Inactivity test | Should | **N** |
| NFR-14 | After 5 failed sign-ins within 15 min, block 15 min; message does not reveal whether the email exists | Wrong password ×5 | Should | **N** |

## 5. Detection engine requirements (ENG-1…ENG-13)

These refine DET-1/DET-2 and are owned by the detection-engine workstream (Design Description v1.1 §6.1).
**Status (2026-11-16): engine code exists (`video_grounding/`, integrated as the `videojev` adapter); per-requirement status not re-assessed. The KPI check on the held-out long-video benchmark ran 2026-11-20 to 22 (Charades-STA is reference only, in-domain): recall 0.86 cooking (CI 0.81–0.90, not confirmed) and 0.47 driving vs 0.85, CCR 0.78 and 0.82 vs 0.85, targets not met; see `video_grounding/docs/EVALUATION.md`.**

| ID | Requirement (short) | Priority |
|---|---|---|
| ENG-1 | Training-free detection with a pretrained video model, no fine-tuning/LoRA/extra heads | Must |
| ENG-2 | Open prompts; several prompts per run, each reported separately; English reference | Must |
| ENG-3 | Return **all** occurrences, including repeated ones | Must |
| ENG-4 | Full coverage: every second analysed by ≥ 1 window; gaps reported | Must |
| ENG-5 | Source timestamps in seconds; correct for VFR/rotation; alignment status exact/estimated/unknown | Must |
| ENG-6 | Complete vs unknown events; review flags with reasons (video edge, window edge, sparse sampling, coverage gap, sound-dependent) | Must |
| ENG-7 | Frame-accurate MP4 clips with configurable margin (default 0.5 s), stored separately; atomic file creation | Must |
| ENG-8 | Keep raw scores + sampling times to re-threshold without re-running the model | Should |
| ENG-9 | Resume interrupted runs without reprocessing finished windows; stable event IDs | Must |
| ENG-10 | Replaceable model and hardware profiles (GPU server, low-VRAM, replay without GPU) | Should |
| ENG-11 | Low-memory fallback reduces frames down to 4 and records it | Should |
| ENG-12 | Offline operation once weights are downloaded; no video leaves the machine | Must |
| ENG-13 | Long videos up to 30 min processed window by window without loading the whole video on GPU | Should |

## 6. KPIs (proposed, to confirm with the customer)

| KPI | Definition | Proposed target |
|---|---|---|
| Precision (accept rate) | Share of reviewed candidates accepted | Reported; target TBD |
| Complete clip rate | Accepted candidates whose clip contains the whole event | ≥ 0.85 |
| Boundary adjustment | Mean seconds reviewers move start/end of accepted candidates | Reported; target TBD |
| Event recall | Share of manually marked events found (a candidate overlaps the event at temporal IoU ≥ 0.3), on a fully watched sample | ≥ 0.85 |
| False candidates on absent prompts | Candidates returned for prompts whose event never happens in the videos (reviewer time wasted) | Reported; target TBD |
| R@IoU 0.3/0.5/0.7, mIoU | Strict boundary overlap; diagnostic only | Reported, no target |
| Engine real-time factor (RTF) | For one video × one prompt, engine wall-clock processing time divided by that video’s duration; RTF < 1 means faster than the video duration | Required reporting; target TBD after 10–30 min video measurements |
| Upload-to-candidates latency | Elapsed time from upload completion to candidates and their preview clips being available, or a successful zero-candidate result; includes queueing and backend work | Required reporting; target TBD after 10–30 min video measurements |
| Per-stage processing time | Seconds spent in queueing, model loading, coarse scan, refinement, optional verification, preview extraction and result persistence | Required reporting; diagnostic, no separate target |

For speed measurements, use **one video × one prompt per job** and report actual processing seconds and
seconds / video duration for that pair. Do not use multi-prompt job totals or divide them by prompt count to
infer product speed. Record the exact prompt, hardware (GPU/VRAM and CPU/RAM), code/model revision, video
duration/resolution, config, verification setting, model-loaded state and initial video-cache state. Separate
model cold starts, model-warm/cache-empty searches and searches reusing visual features. Report Recall and
complete clip rate under the same configuration. Start processing immediately after upload for the latency
benchmark; report upload transfer and manual delays separately. Report failed jobs and missing preview clips.
For repeated runs of the same pair and state, report sample count, median and p90; for a single observation,
report its individual value without a percentile claim.

Backend job processing time (`finished_at − started_at`) excludes pre-claim queueing and is reported as a
single-prompt job time/RTF, separately from full engine RTF and upload-to-candidates latency. Current measured
pairs, prompts, model/cache states and sample sizes are in [the speed report](../video_grounding/docs/EVALUATION.md#speed-kpis).

*2026-11-16: R@IoU=0.5 ≥ 0.70 dropped as a target. This is an engineering tool, not a research benchmark: candidates only need to land in a reasonable range, because reviewers correct and confirm the span. Whether a span is good enough is measured by the complete clip rate (2 s tolerance per end) and the boundary adjustment.*

## 7. User stories

| ID | Story | Requirements | Priority |
|---|---|---|---|
| US-1 | Build a dataset: create, upload ≥ 3 HD MP4 (~5 min), see the list | DS-1/2/4/5, NFR-4 | Must |
| US-2 | Search for an event: select dataset, prompt, background search, candidates within 24 h | DS-3, PR-1/2, DET-1/2/3, NFR-3 | Must |
| US-3 | Review candidates: all videos in one list, preview, adjust timestamps, accept/reject, counter | REV-1…4, DET-4, NFR-2/7 | Must |
| US-4 | Export annotations: choose dataset (and optionally prompt), JSON, optional rejected | EXP-1/2 | Must |
| US-5 | Manage access: invite by email + role, assign datasets, reset password, sign out/expiry/lockout | USR-1…7, NFR-11…14 | Must |
| US-6 | Search videos by scene | SRCH-1 | Could |
| US-7 | Review video summary and tags | EXP-3/4 | Could |

## 8. Out of scope

Training models from scratch · real-time detection · advanced semantic search · advanced dataset
administration and large-collection tools · annotation/label reuse across users and datasets ·
administrator-controlled access to sensitive faces · file access history/activity tracking · Viewer role.

## 9. Assumptions and open questions

Assumptions: videos are single-view RGB; one prompt = one search; a dataset is a collection of videos and a
video belongs to one dataset; one reviewer per candidate; roles are per user (global); accounts are created by
invitation.

| # | Open question | Affects | Owner | Status |
|---|---|---|---|---|
| 1 | May face-containing videos be sent to Gemini? Conditions? | NFR-8, DET-1 | Customer | **Open — ask 13 Nov** |
| 2 | Must the export record the reviewer? One reviewer per candidate? | EXP-1, REV-3 | Customer | **Open (asked, not answered)** |
| 3 | Dataset = uploaded videos, labelled output, or both? Video in several datasets? | DS-1/2, EXP-1 | Customer | Open |
| 4 | Confirm the JSON field list; MP4 clips in the export? | EXP-1 | Customer | Open — proposal due 17 Nov |
| 5 | Include rejected candidates as negatives? | EXP-2 | Customer | Open |
| 6 | Confirm 5-min/720p-1080p MVP and no audio | DS-4/5, NFR-4 | Customer | Open |
| 7 | Session limits 2 h / 5 attempts / 15 min | NFR-13/14 | Customer | Open |
| 8 | Mobile review still needed? | NFR-2 | Customer | Open |
| 9 | Confirm KPI targets | NFR-5 | Customer/team | Open |
| 10 | Test datasets and licence for commercial use | NFR-5/8 | Customer | Open |
| 11 | Hosting and compute provider; 12 GB vs 24 GB GPU | NFR-3/10 | Customer/supervisors | Open |
| 12 | Retention/deletion rules | NFR-8 | Customer | Open |
| 13 | **Answered in CE-2:** global roles; email-only accounts; Dataset Admins may invite; Dataset Admins can create/upload/export | §2, USR-1/4/5 | — | **Closed** |

## 10. Implementation traceability (summary)

| Requirement group | Current code | Tests |
|---|---|---|
| DS-1/2/3, DS-4/5 | `backend/app/api/videos.py`, `projects.py`; `services/storage.py`, `media.py` | `test_api_videos.py`, smoke |
| PR-1 | `models.Search`/`SearchVideo`, `api/searches.py` | `test_searches.py` (fan-out, status aggregation, idempotency request scope, cancel/restart) |
| DET-2/3/4 | `services/pipeline.py`, `worker.py`, `models.ProcessingJob/Candidate` | `test_flow.py`, `test_worker.py` |
| REV-1…4 | `api/candidates.py`, `frontend/src/pages/ReviewPage.tsx` | `test_flow.py`, UI E2E report |
| EXP-1/2 | `services/pipeline.py` (ZIP export) — **needs rewrite to JSON** | `test_flow.py` |
| USR-1…5 | `api/auth.py`, `security.py`, `deps.py`, `models.User/Invitation/UserSession` | `test_auth.py` |
| DS-1/2/3 (access) | `api/datasets.py`, `app/access.py`, `models.Dataset/DatasetMembership` | `test_datasets.py`, `test_auth.py`, `test_dataset_authz.py` |
| NFR-8 | generated storage keys, deletion, token | `test_storage.py` |

> The **authoritative submission** for 2026-11-13 is the team's PDF (v1.1 or a regenerated v1.2). This
> repository copy exists so the source stays editable, reviewable and traceable to the code.
